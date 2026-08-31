"""Unified fantasy read API + the `sync_discovery` write path (tasks 3.9/3.12).

Two very different halves, by design (design.md D7):

- **Writes** (`refresh_discovery`) are the only functions that talk to Yahoo/ESPN. They
  run under the scheduler (or the manual `POST /api/admin/refresh`), fan out across the
  connected platforms in parallel, map raw payloads via the pure platform mappers, and
  upsert normalized rows. A failure on one platform never blocks the other — it's
  recorded (module-level `_LAST_ERRORS`, surfaced via `meta.platforms`) and never raised.

- **Reads** (`list_teams` / `get_team` / `get_h2h` / `get_season` / `build_meta`) NEVER
  fetch upstream. They only assemble responses from the persisted normalized tables, so
  page loads are instant and independent of upstream latency.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron import schemas
from backend.gridiron.config import Settings, get_settings
from backend.gridiron.errors import AuthRequiredError, CredentialDecryptError, RateLimitedError
from backend.gridiron.models import (
    Connection,
    Headshot,
    HttpCache,
    League,
    LiveNflGame,
    Matchup,
    MatchupSlot,
    Player,
    PlayerPoolEntry,
    RefreshRun,
    RosterSlot,
    SeasonWeek,
    Team,
)
from backend.gridiron.platforms.espn import mapper as espn_mapper
from backend.gridiron.platforms.espn.client import EspnClient
from backend.gridiron.platforms.yahoo import mapper as yahoo_mapper
from backend.gridiron.platforms.yahoo.client import YahooClient
from backend.gridiron.services import cache as cache_service
from backend.gridiron.services import credentials, differ
from backend.gridiron.services import live_state as live_state_service

logger = logging.getLogger("uvicorn.error")

PLATFORMS: tuple[str, ...] = ("yahoo", "espn")

# Every user team gets the Fitness-pink accent for now (task 3.9); a per-team picker is a
# later Settings feature.
ACCENT_COLOR = "#FF2D55"

STARTER_EXCLUDED_SLOTS = ("BN", "IR")
# Display/sort order. Every value in `schemas.Slot` must appear here: `_SLOT_RANK.get`
# falls back to `len(SLOT_ORDER)` for anything missing, which gives every unlisted slot
# an IDENTICAL rank — they would sort after DST in whatever order the query happened to
# return, with no test able to see it (`sorted` is stable, so it looks plausible).
SLOT_ORDER = [
    "QB",
    "RB1",
    "RB2",
    "WR1",
    "WR2",
    "TE",
    "FLEX",
    "FLEX1",
    "FLEX2",
    "FLEX3",
    "FLEX4",
    "OP1",
    "OP2",
    "K",
    "DST",
    "BN",
    "IR",
]
_SLOT_RANK = {slot: i for i, slot in enumerate(SLOT_ORDER)}

# Adaptive backoff (live-updates spec): a platform that rate-limits or 5xxes during a
# refresh run is skipped by subsequent runs until `cooldown_until`.
COOLDOWN = timedelta(minutes=5)

# Module-level per-platform refresh state. Single-process, single-user app (design.md D1)
# — this is deliberately in-memory, not persisted; a restart clears it and the next
# scheduled run rebuilds it.
_LAST_ERRORS: dict[str, str | None] = {}
_COOLDOWN_UNTIL: dict[str, datetime] = {}


def reset_state() -> None:
    """Clear module-level refresh state (used by tests)."""
    _LAST_ERRORS.clear()
    _COOLDOWN_UNTIL.clear()


def set_cooldown(platform: str, until: datetime | None = None) -> None:
    _COOLDOWN_UNTIL[platform] = until or (datetime.now(UTC) + COOLDOWN)


# --------------------------------------------------------------------------------------
# Response payload shapes (the `data` half of the envelope, per fantasy-data-model spec)
# --------------------------------------------------------------------------------------


class TeamsData(BaseModel):
    teams: list[schemas.Team]


class TeamDetailData(BaseModel):
    team: schemas.Team
    league: schemas.League
    starters: list[schemas.RosterSlot]
    bench: list[schemas.RosterSlot]
    record_history: list[schemas.SeasonWeek]


class Remaining(BaseModel):
    mine: int
    theirs: int


class H2HData(BaseModel):
    matchup: schemas.Matchup
    slots: list[schemas.MatchupSlot]
    remaining: Remaining


class GameDayMatchup(BaseModel):
    """One user team's complete head-to-head, flattened onto the user's perspective.

    Everything is already oriented — `team_*` is always the user's side and `opp_*` the
    opponent's, whichever side of `matchups` they sit on — so the consumer never
    re-derives home/away for the panel-level values. `slots` keeps the raw home/away
    `MatchupSlot` shape and is oriented client-side via `orientSlot(slot, iAmHome)`,
    which the Head-to-Head screen already owns.

    No `win_prob` (design D7): the endpoint returns `proj`, `opp_proj` and `remaining`
    — the only three inputs the client's `computeProjectedFinal` takes — so a
    server-side copy would mean maintaining a second implementation of that model.
    """

    team_id: str
    team_name: str
    opp_team_id: str
    opp_team_name: str
    league_id: str
    league_name: str
    # Derived from the team id's `{platform}:` prefix — `Team` carries no `platform`
    # field (design D5).
    platform: str
    record: schemas.Record
    rank: schemas.Rank
    score: float
    opp_score: float
    proj: float
    opp_proj: float
    remaining: Remaining
    is_complete: bool
    # Which side of the underlying matchup the user's team sits on. Everything else on
    # this model is already oriented, but `slots` deliberately keeps the raw home/away
    # shape so the client can reuse Head-to-Head's `orientSlot(slot, iAmHome)` — and
    # `MatchupSlot` carries no team ids, so without this flag that call has no input and
    # the slots are unorientable. (Additive to the field list in the spec's "Bulk
    # game-day matchups" scenario, which that scenario's own "Orientation" requirement
    # in specs/game-day/spec.md implicitly needs.)
    i_am_home: bool
    slots: list[schemas.MatchupSlot]


class GameDayData(BaseModel):
    matchups: list[GameDayMatchup]


class MostStarted(BaseModel):
    player: schemas.Player
    starts: int
    avg_points: float


class Highlights(BaseModel):
    season_high: schemas.SeasonWeek | None
    win_streak: int
    most_started: MostStarted | None


class SeasonData(BaseModel):
    weeks: list[schemas.SeasonWeek]
    highlights: Highlights


@dataclass
class PlatformOutcome:
    ok: bool
    error: str | None = None


# --------------------------------------------------------------------------------------
# ORM row -> schema converters
# --------------------------------------------------------------------------------------


def _headshot_url(platform: str, platform_id: str) -> str:
    """Derive the local headshot URL by convention. The trailing id segment works for both
    platforms: espn platform_ids are already bare numerics, yahoo player_keys end in the
    global player id (`461.p.30123` -> `30123`)."""
    return f"/api/headshots/{platform}/{platform_id.rsplit('.', 1)[-1]}.png"


def _player_schema(row: Player) -> schemas.Player:
    return schemas.Player(
        id=row.id,
        name=row.name,
        position=row.position,
        nfl_team=row.nfl_team,
        nfl_opponent=row.nfl_opponent,
        nfl_game_id=row.nfl_game_id,
        headshot_url=_headshot_url(row.platform, row.platform_id),
        bye_week=row.bye_week,
        injury_status=row.injury_status,
    )


def _roster_slot_schema(row: RosterSlot, player: Player) -> schemas.RosterSlot:
    return schemas.RosterSlot(
        team_id=row.team_id,
        week=row.week,
        slot=row.slot,
        player=_player_schema(player),
        proj_points=row.proj_points,
        actual_points=row.actual_points,
        is_live=row.is_live,
        game_state=row.game_state,
        status_text=row.status_text,
    )


def _matchup_schema(row: Matchup) -> schemas.Matchup:
    return schemas.Matchup(
        id=row.id,
        league_id=row.league_id,
        week=row.week,
        home_team_id=row.home_team_id,
        away_team_id=row.away_team_id,
        home_score=row.home_score,
        away_score=row.away_score,
        home_proj=row.home_proj,
        away_proj=row.away_proj,
        is_complete=row.is_complete,
    )


def _season_week_schema(row: SeasonWeek) -> schemas.SeasonWeek:
    return schemas.SeasonWeek(
        team_id=row.team_id,
        week=row.week,
        score=row.score,
        opp_score=row.opp_score,
        opp_team_name=row.opp_team_name,
        is_win=row.is_win,
        is_current=row.is_current,
    )


def _league_schema(row: League) -> schemas.League:
    return schemas.League(
        id=row.id,
        platform=row.platform,
        platform_id=row.platform_id,
        name=row.name,
        season=row.season,
        team_count=row.team_count,
        scoring_type=row.scoring_type,
        current_week=row.current_week,
    )


async def _live_nfl_teams(session: AsyncSession) -> set[str]:
    """NFL team abbreviations currently in an in-progress game (`live_nfl_games.state ==
    "in"`), fed by the `refresh_nfl_state` scheduler job. Feeds `_team_schema`'s
    `is_live` — a team is "live" when it has a rostered (non-bench) starter on one of
    these NFL teams this week. Empty (never polled / off day / no games in progress)
    degrades every team to `is_live=False` by construction — see `_team_is_live`."""
    rows = (
        await session.execute(
            select(LiveNflGame.home_team, LiveNflGame.away_team).where(LiveNflGame.state == "in")
        )
    ).all()
    teams: set[str] = {abbr for pair in rows for abbr in pair if abbr}
    return teams


async def _team_is_live(
    session: AsyncSession, team_id: str, week: int, live_nfl_teams: set[str]
) -> bool:
    """Is any of `team_id`'s week-`week` starters (non-BN/IR) on an NFL team currently
    live? Degrades to `False` when `live_nfl_teams` is empty (no live_nfl_games polled
    yet, or nothing in progress right now) without even issuing a query, and also
    degrades to `False` when a platform's rosters don't carry a usable `nfl_team`
    abbreviation for this week (an empty/mismatched value simply never matches
    `live_nfl_teams`, which only ever contains real ESPN-scoreboard abbreviations)."""
    if not live_nfl_teams:
        return False
    count = (
        await session.execute(
            select(func.count())
            .select_from(RosterSlot)
            .join(Player, RosterSlot.player_id == Player.id)
            .where(
                RosterSlot.team_id == team_id,
                RosterSlot.week == week,
                RosterSlot.slot.not_in(STARTER_EXCLUDED_SLOTS),
                Player.nfl_team.in_(live_nfl_teams),
            )
        )
    ).scalar()
    return bool(count)


async def _team_schema(
    session: AsyncSession, row: Team, week: int, live_nfl_teams: set[str] | None = None
) -> schemas.Team:
    """Build the D12 `Team` shape from a `teams` row, overlaying the week-scoped fields the
    mappers left defaulted: current_score / current_opp_score / current_opponent_name from
    the week's `matchups` row, spark_last_6 from `season_weeks`, and the accent color.

    `live_nfl_teams` is `_live_nfl_teams(session)`'s result — callers that build several
    teams in one pass (`list_teams`) compute it once and pass it through rather than
    re-querying `live_nfl_games` per team; a lone caller (`get_team`) may omit it and let
    this function fetch it itself.
    """
    if live_nfl_teams is None:
        live_nfl_teams = await _live_nfl_teams(session)
    current_score = 0.0
    current_opp_score = 0.0
    current_opponent_name = ""

    matchup = (
        await session.execute(
            select(Matchup).where(
                Matchup.week == week,
                (Matchup.home_team_id == row.id) | (Matchup.away_team_id == row.id),
            )
        )
    ).scalar_one_or_none()
    if matchup is not None:
        if matchup.home_team_id == row.id:
            current_score, current_opp_score = matchup.home_score, matchup.away_score
            opp_id = matchup.away_team_id
        else:
            current_score, current_opp_score = matchup.away_score, matchup.home_score
            opp_id = matchup.home_team_id
        opp = await session.get(Team, opp_id)
        current_opponent_name = opp.name if opp is not None else ""

    spark_rows = (
        await session.execute(
            select(SeasonWeek.score)
            .where(SeasonWeek.team_id == row.id, SeasonWeek.week <= week)
            .order_by(SeasonWeek.week.desc())
            .limit(6)
        )
    ).scalars()
    spark_last_6 = list(reversed(list(spark_rows)))

    return schemas.Team(
        id=row.id,
        league_id=row.league_id,
        name=row.name,
        manager_name=row.manager_name,
        record=schemas.Record(w=row.record_w, l=row.record_l, t=row.record_t),
        rank=schemas.Rank(current=row.rank_current, total=row.rank_total),
        points_for=row.points_for,
        points_against=row.points_against,
        is_user_team=row.is_user_team,
        current_score=current_score,
        current_opp_score=current_opp_score,
        current_opponent_name=current_opponent_name,
        is_live=await _team_is_live(session, row.id, week, live_nfl_teams),
        spark_last_6=spark_last_6,
        accent_color=ACCENT_COLOR,
    )


# --------------------------------------------------------------------------------------
# Reads (never fetch upstream — design.md D7)
# --------------------------------------------------------------------------------------


async def current_week(session: AsyncSession) -> int:
    """Default week when the request doesn't pass one: max `current_week` across persisted
    leagues, falling back to 1 on an empty database."""
    week = (await session.execute(select(func.max(League.current_week)))).scalar()
    return int(week) if week else 1


async def list_teams(session: AsyncSession, week: int) -> list[schemas.Team]:
    """The user's teams across every platform, with week-scoped overlays applied.

    Excludes teams whose league has been disabled from the Settings "ESPN Leagues" card
    (task 7.3) — the league/team rows stay in the database (so re-enabling is instant),
    they're just filtered out of this aggregation.
    """
    rows = (
        (
            await session.execute(
                select(Team)
                .join(League, Team.league_id == League.id)
                .where(Team.is_user_team.is_(True), League.is_enabled.is_(True))
                .order_by(Team.league_id, Team.id)
            )
        )
        .scalars()
        .all()
    )
    live_nfl_teams = await _live_nfl_teams(session)
    return [await _team_schema(session, row, week, live_nfl_teams) for row in rows]


# --------------------------------------------------------------------------------------
# Day rings (task 10.6) — Topbar's day-of-week rings, from real scoring data.
# --------------------------------------------------------------------------------------

# design/data.jsx's WEEK_DAYS letter order: Thursday, Friday, Saturday, Sunday, Monday —
# the NFL's standard game-day span for a week.
_DAY_LETTERS = ["T", "F", "S", "S", "M"]


class DayRingValue(BaseModel):
    value: float
    color: str


class DayRing(BaseModel):
    letter: str
    rings: list[DayRingValue]


class DayRingsData(BaseModel):
    days: list[DayRing]
    today_index: int | None


def _nfl_week_days(today: date) -> list[date]:
    """The Thu-Mon calendar span containing `today` — `date.weekday()` is Mon=0..Sun=6,
    so Thursday is 3."""
    days_since_thursday = (today.weekday() - 3) % 7
    thursday = today - timedelta(days=days_since_thursday)
    return [thursday + timedelta(days=i) for i in range(5)]


async def _current_week_game_day_by_nfl_team(
    session: AsyncSession, day_span: list[date]
) -> dict[str, date]:
    """NFL team abbreviation -> the calendar date (one of `day_span`) its game kicks off
    on, from `live_nfl_games`.

    `live_nfl_games` carries no explicit week number (it's just "whatever ESPN's public
    scoreboard shows right now") and `nfl_scoreboard.upsert_games` deliberately never
    deletes a row that's dropped off the scoreboard (a bye week, a canceled game) — so a
    team can have a stale prior-week row lingering alongside its current one. Only
    trusting a row whose `kickoff_at` actually falls in `day_span` filters out both that
    staleness and any accidental future-week leakage in one pass.
    """
    rows = (await session.execute(select(LiveNflGame))).scalars().all()
    by_team: dict[str, date] = {}
    for row in rows:
        kickoff_date = row.kickoff_at.date()
        if kickoff_date in day_span:
            by_team[row.home_team] = kickoff_date
            by_team[row.away_team] = kickoff_date
    return by_team


async def day_rings(session: AsyncSession, week: int, today: date | None = None) -> DayRingsData:
    """Per-day scoring rings for the Topbar (task 10.6): one ring per user team for each
    calendar day in the current Thu-Mon NFL week window, valued as that day's share of
    the team's `week` score so far (0..1, like every other `ActivityRing` track).

    Two real gaps this degrades around rather than fabricating data for:
    - No live_nfl_games ever polled (fresh DB, or the off-season) -> every ring is 0.
      The day-letter skeleton itself is always real (today's actual calendar span), only
      the fill amounts are unknown, matching the "empty rings" degrade the task calls
      for rather than hiding the row entirely.
    - A team with `current_score == 0` this week (bye, or simply hasn't started yet) ->
      every one of its rings is 0 rather than a division-by-zero.

    `today` defaults to the real current date; tests pass a fixed one for determinism.
    """
    today = today or datetime.now(UTC).date()
    day_span = _nfl_week_days(today)
    today_index = day_span.index(today) if today in day_span else None

    game_day_by_team = await _current_week_game_day_by_nfl_team(session, day_span)

    team_rows = (
        (
            await session.execute(
                select(Team)
                .join(League, Team.league_id == League.id)
                .where(Team.is_user_team.is_(True), League.is_enabled.is_(True))
                .order_by(Team.league_id, Team.id)
            )
        )
        .scalars()
        .all()
    )

    day_points_by_team: dict[str, dict[date, float]] = {}
    total_points_by_team: dict[str, float] = {}
    for team in team_rows:
        slot_rows = (
            await session.execute(
                select(RosterSlot.actual_points, Player.nfl_team)
                .join(Player, RosterSlot.player_id == Player.id)
                .where(
                    RosterSlot.team_id == team.id,
                    RosterSlot.week == week,
                    RosterSlot.slot.not_in(STARTER_EXCLUDED_SLOTS),
                )
            )
        ).all()
        day_points: dict[date, float] = {}
        total = 0.0
        for actual_points, nfl_team in slot_rows:
            total += actual_points
            game_day = game_day_by_team.get(nfl_team)
            if game_day is not None:
                day_points[game_day] = day_points.get(game_day, 0.0) + actual_points
        day_points_by_team[team.id] = day_points
        total_points_by_team[team.id] = total

    days: list[DayRing] = []
    for letter, day in zip(_DAY_LETTERS, day_span, strict=True):
        rings = []
        for team in team_rows:
            total = total_points_by_team.get(team.id, 0.0)
            points = day_points_by_team.get(team.id, {}).get(day, 0.0)
            value = max(0.0, min(1.0, points / total)) if total > 0 else 0.0
            rings.append(DayRingValue(value=value, color=ACCENT_COLOR))
        days.append(DayRing(letter=letter, rings=rings))

    return DayRingsData(days=days, today_index=today_index)


async def get_team(session: AsyncSession, team_id: str, week: int) -> TeamDetailData | None:
    """Team detail per the fantasy-data-model spec: team + league + starters/bench roster +
    record history. Returns `None` for an unknown team id (the API layer 404s)."""
    team_row = await session.get(Team, team_id)
    if team_row is None:
        return None
    league_row = await session.get(League, team_row.league_id)

    slot_rows = (
        await session.execute(
            select(RosterSlot, Player)
            .join(Player, RosterSlot.player_id == Player.id)
            .where(RosterSlot.team_id == team_id, RosterSlot.week == week)
        )
    ).all()
    slots = sorted(
        (_roster_slot_schema(rs, player) for rs, player in slot_rows),
        key=lambda s: _SLOT_RANK.get(s.slot, len(SLOT_ORDER)),
    )
    starters = [s for s in slots if s.slot not in STARTER_EXCLUDED_SLOTS]
    bench = [s for s in slots if s.slot in STARTER_EXCLUDED_SLOTS]

    history_rows = (
        (
            await session.execute(
                select(SeasonWeek).where(SeasonWeek.team_id == team_id).order_by(SeasonWeek.week)
            )
        )
        .scalars()
        .all()
    )

    return TeamDetailData(
        team=await _team_schema(session, team_row, week),
        league=_league_schema(league_row),
        starters=starters,
        bench=bench,
        record_history=[_season_week_schema(r) for r in history_rows],
    )


def _base_slot(slot: str) -> str:
    """`RB1` -> `RB`, `FLEX2` -> `FLEX`, `QB` -> `QB`.

    Bridges the two slot vocabularies. Internal `Slot` labels are numbered by
    per-roster counters (`_internal_slot`); the platform's `eligibleSlots` are the
    same names unnumbered, because a player off a roster has no counter context. The
    unnumbered form is what the two can be compared on.
    """
    return slot.rstrip("0123456789")


def _startable_eligibility(eligible_slots: list[str]) -> set[str]:
    """The candidate's eligible slots, minus the ones that are not starting spots.

    The platform lists `BN` and `IR` as eligible for essentially every player — a live
    pull returns `['RB', 'RB/WR', 'FLEX', 'OP', 'BN', 'IR']` for a running back — so
    leaving them in would make every candidate "contest" every bench spot, and the
    weakest-starter comparison would silently match against a benched player.
    """
    return {s for s in eligible_slots if s not in STARTER_EXCLUDED_SLOTS}


async def get_waivers(
    session: AsyncSession,
    team_id: str,
    week: int,
    position: str | None = None,
    limit: int = 50,
) -> schemas.WaiversData | None:
    """Claimable players in this team's league, ranked, each measured against the
    starter it would actually replace. `None` for an unknown team (the API layer 404s).
    """
    team_row = await session.get(Team, team_id)
    if team_row is None:
        return None
    league_id = team_row.league_id

    # 1 of 2 queries: the user's current starters, each with its SEASON projection
    # joined from the pool. Deliberately an outer join — a starter missing a pool row
    # (a sync that has not run) must leave the delta null, not drop the starter.
    starter_rows = (
        await session.execute(
            select(RosterSlot.slot, PlayerPoolEntry.season_proj_points)
            .outerjoin(
                PlayerPoolEntry,
                (PlayerPoolEntry.player_id == RosterSlot.player_id)
                & (PlayerPoolEntry.league_id == league_id),
            )
            .where(
                RosterSlot.team_id == team_id,
                RosterSlot.week == week,
                RosterSlot.slot.not_in(STARTER_EXCLUDED_SLOTS),
            )
        )
    ).all()
    # base slot -> the season projections of the user's starters occupying it
    starters_by_slot: dict[str, list[float]] = {}
    for slot, proj in starter_rows:
        if proj is not None:
            starters_by_slot.setdefault(_base_slot(slot), []).append(proj)

    # 2 of 2: the candidates themselves. ONTEAM rows are ingested for the comparison
    # above and are never claimable, so they are excluded here.
    stmt = (
        select(PlayerPoolEntry, Player)
        .join(Player, PlayerPoolEntry.player_id == Player.id)
        .where(
            PlayerPoolEntry.league_id == league_id,
            PlayerPoolEntry.status.in_(("FREEAGENT", "WAIVERS")),
        )
    )
    if position is not None:
        stmt = stmt.where(Player.position == position)

    # Ranking happens in Python, not SQL, because the sort key is the delta — and the
    # delta is not a column. Ordering by `season_proj_points` in SQL and slicing to
    # `limit` there produces a leaderboard of raw scorers: against real data every top
    # row came back a quarterback with a NEGATIVE delta, i.e. eight players worse than
    # the one already started. That is exactly the uselessness the delta exists to
    # avoid, so it has to drive the order, not just decorate it.
    #
    # Bounded by construction: one league's pool is ~1000 rows, loaded once, and only
    # `limit` of them are turned into schemas.
    scored: list[tuple[float | None, float | None, PlayerPoolEntry, Player, list[str]]] = []
    for entry, player in (await session.execute(stmt)).all():
        eligible = json.loads(entry.eligible_slots or "[]")
        contested = [
            proj
            for slot, projs in starters_by_slot.items()
            if slot in _startable_eligibility(eligible)
            for proj in projs
        ]

        # Null, never 0.0: "no comparison available" and "exactly as good as the
        # weakest starter" are different answers, and both occur.
        delta = None
        if entry.season_proj_points is not None and contested:
            delta = entry.season_proj_points - min(contested)

        scored.append((delta, entry.season_proj_points, entry, player, eligible))

    # Biggest upgrade first; unrankable rows (no delta, then no projection) last.
    # Projection breaks ties, so two equal upgrades order by the better player.
    scored.sort(
        key=lambda row: (
            row[0] is None,
            -(row[0] if row[0] is not None else 0.0),
            row[1] is None,
            -(row[1] if row[1] is not None else 0.0),
        )
    )

    candidates = [
        schemas.WaiverCandidate(
            league_id=league_id,
            player=_player_schema(player),
            status=entry.status,
            on_team_id=entry.on_team_id,
            percent_owned=entry.percent_owned,
            percent_started=entry.percent_started,
            season_proj_points=entry.season_proj_points,
            eligible_slots=eligible,
            delta_vs_worst_starter=delta,
        )
        for delta, _proj, entry, player, eligible in scored[:limit]
    ]

    return schemas.WaiversData(
        team_id=team_id, league_id=league_id, week=week, candidates=candidates
    )


def _slot_is_remaining(game_state: str | None) -> bool:
    """A starter counts as "yet to play" until its NFL game is final. Discovery leaves
    `game_state` NULL (pre-classification), which counts as not-finished."""
    return game_state != "post"


async def _per_side_slot_state(
    session: AsyncSession, team_ids: list[str], week: int
) -> dict[tuple[str, str], tuple[str | None, bool]]:
    """`(team_id, player_id) -> (game_state, is_live)` for one week's roster slots.

    This is the join behind `MatchupSlot`'s per-side state (design D6). The key is
    **player identity, not the slot label**: the Yahoo path pairs matchup slots by
    internal slot label (`_pair_matchup_slots`) while the ESPN path receives them
    natively from `espn.mapper.map_matchup`, so slot labels are not comparable across
    platforms.

    `team_id` is part of the key because `(player_id, week)` alone is **not** unique —
    `roster_slots`' constraint is `uq_roster_slots_team_week_player`, so one player
    rostered in two of the user's leagues has one row per team. Scoping the lookup by
    the matchup's own home/away team ids keeps the join on player identity (D6's actual
    requirement) while matching the uniqueness that really holds. Joining on
    `(player_id, week)` alone would let a multi-league player pick up the wrong league's
    state.

    Takes a list of team ids so callers building many matchups at once (`game_day`) load
    every side in one query rather than one query per team.
    """
    if not team_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(RosterSlot).where(RosterSlot.team_id.in_(team_ids), RosterSlot.week == week)
            )
        )
        .scalars()
        .all()
    )
    return {(r.team_id, r.player_id): (r.game_state, r.is_live) for r in rows}


def _matchup_slot_schema(
    row: MatchupSlot,
    players: dict[str, Player],
    state: dict[tuple[str, str], tuple[str | None, bool]],
    home_team_id: str,
    away_team_id: str,
) -> schemas.MatchupSlot:
    """Build the read-path `MatchupSlot`, overlaying each side's live state from the
    `roster_slots` row for that (team, player). A player with no roster row that week
    falls back to `(None, False)` — unclassified, not live."""
    home_state, home_is_live = state.get((home_team_id, row.home_player_id), (None, False))
    away_state, away_is_live = state.get((away_team_id, row.away_player_id), (None, False))
    return schemas.MatchupSlot(
        matchup_id=row.matchup_id,
        slot=row.slot,
        home_player=_player_schema(players[row.home_player_id]),
        away_player=_player_schema(players[row.away_player_id]),
        home_pts=row.home_pts,
        away_pts=row.away_pts,
        home_state=home_state,
        away_state=away_state,
        home_is_live=home_is_live,
        away_is_live=away_is_live,
    )


async def _remaining_count(session: AsyncSession, team_id: str, week: int) -> int:
    """Starters whose NFL game hasn't finished (game_state != 'post'). Discovery leaves
    game_state NULL (pre-classification), which counts as not-finished."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(RosterSlot)
            .where(
                RosterSlot.team_id == team_id,
                RosterSlot.week == week,
                RosterSlot.slot.not_in(STARTER_EXCLUDED_SLOTS),
                (RosterSlot.game_state.is_(None)) | (RosterSlot.game_state != "post"),
            )
        )
    ).scalar()
    return int(count or 0)


async def get_h2h(session: AsyncSession, team_id: str, week: int) -> H2HData | None:
    """Head-to-head detail: the week's matchup, its slot pairings, and remaining-player
    counts. Returns `None` when the team is unknown or has no matchup that week."""
    team_row = await session.get(Team, team_id)
    if team_row is None:
        return None

    matchup_row = (
        await session.execute(
            select(Matchup).where(
                Matchup.week == week,
                (Matchup.home_team_id == team_id) | (Matchup.away_team_id == team_id),
            )
        )
    ).scalar_one_or_none()
    if matchup_row is None:
        return None

    slot_rows = (
        (await session.execute(select(MatchupSlot).where(MatchupSlot.matchup_id == matchup_row.id)))
        .scalars()
        .all()
    )
    player_ids = {s.home_player_id for s in slot_rows} | {s.away_player_id for s in slot_rows}
    players = {
        p.id: p
        for p in (await session.execute(select(Player).where(Player.id.in_(player_ids))))
        .scalars()
        .all()
    }
    state = await _per_side_slot_state(
        session, [matchup_row.home_team_id, matchup_row.away_team_id], week
    )
    slots = sorted(
        (
            _matchup_slot_schema(
                s, players, state, matchup_row.home_team_id, matchup_row.away_team_id
            )
            for s in slot_rows
        ),
        key=lambda s: _SLOT_RANK.get(s.slot, len(SLOT_ORDER)),
    )

    opp_id = (
        matchup_row.away_team_id
        if matchup_row.home_team_id == team_id
        else matchup_row.home_team_id
    )
    remaining = Remaining(
        mine=await _remaining_count(session, team_id, week),
        theirs=await _remaining_count(session, opp_id, week),
    )
    return H2HData(matchup=_matchup_schema(matchup_row), slots=slots, remaining=remaining)


async def game_day(session: AsyncSession, week: int) -> GameDayData:
    """Every matchup involving a user team for `week`, each already oriented onto that
    user team's perspective — the bulk read behind the Game Day screen (design D5).

    Replaces what would otherwise be one `/h2h` + one `/{id}` request per team (twelve
    for a six-league user) with a single envelope, so an SSE tick costs one refetch.

    **Bounded query count** (fantasy-data-model spec, "No N+1"): this issues a fixed
    number of queries regardless of how many teams the user has — the user teams, the
    week's matchups, the teams on both sides, their leagues, the matchup slots, the
    players, and the week's roster slots, each loaded once for the whole set.

    It deliberately does **not** call `_team_schema`, despite tasks.md 2.3 suggesting
    it. `_team_schema` costs roughly four queries *per team* (its own matchup lookup, an
    opponent `session.get`, the sparkline select, and `_team_is_live`) and three of the
    things it computes — `spark_last_6`, `accent_color`, `is_live` — are not on
    `GameDayMatchup` at all. Reusing it would pay all of that cost for a minority of its
    output and break the bounded-query requirement, which is the normative one. The
    fields it *does* share (`record`, `rank`, and the week-scoped
    `score`/`opp_score`/`opp_team_name`) are derived here from the same sources it uses:
    the `teams` row and the week's `matchups` row.

    One entry per *user team*, keyed by `team_id` — so if two of the user's own teams
    happen to meet in the same league, each gets its own panel from its own side.
    """
    # Disabled leagues are excluded, matching `list_teams` and `day_rings` — a league
    # the user has switched off in Settings must not reappear here just because this is
    # a different read. Discovery also skips writing to it, so its rows go stale rather
    # than being deleted, which is exactly why the filter has to live on every read.
    user_teams = (
        (
            await session.execute(
                select(Team)
                .join(League, Team.league_id == League.id)
                .where(Team.is_user_team.is_(True), League.is_enabled.is_(True))
                .order_by(Team.league_id, Team.id)
            )
        )
        .scalars()
        .all()
    )
    if not user_teams:
        return GameDayData(matchups=[])

    user_team_ids = [t.id for t in user_teams]
    matchup_rows = (
        (
            await session.execute(
                select(Matchup).where(
                    Matchup.week == week,
                    Matchup.home_team_id.in_(user_team_ids)
                    | Matchup.away_team_id.in_(user_team_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    if not matchup_rows:
        return GameDayData(matchups=[])

    # One matchup can be the home side of one user team and the away side of another, so
    # index by team id rather than assuming a 1:1 team/matchup mapping.
    matchup_by_team: dict[str, Matchup] = {}
    for m in matchup_rows:
        matchup_by_team.setdefault(m.home_team_id, m)
        matchup_by_team.setdefault(m.away_team_id, m)

    all_team_ids = sorted(
        {m.home_team_id for m in matchup_rows} | {m.away_team_id for m in matchup_rows}
    )
    teams_by_id = {
        t.id: t
        for t in (await session.execute(select(Team).where(Team.id.in_(all_team_ids))))
        .scalars()
        .all()
    }
    league_ids = sorted({t.league_id for t in teams_by_id.values()})
    league_names = {
        row_id: name
        for row_id, name in (
            await session.execute(select(League.id, League.name).where(League.id.in_(league_ids)))
        ).all()
    }

    matchup_ids = [m.id for m in matchup_rows]
    slot_rows = (
        (await session.execute(select(MatchupSlot).where(MatchupSlot.matchup_id.in_(matchup_ids))))
        .scalars()
        .all()
    )
    slots_by_matchup: dict[str, list[MatchupSlot]] = {}
    for row in slot_rows:
        slots_by_matchup.setdefault(row.matchup_id, []).append(row)

    player_ids = {r.home_player_id for r in slot_rows} | {r.away_player_id for r in slot_rows}
    players = {
        pl.id: pl
        for pl in (await session.execute(select(Player).where(Player.id.in_(player_ids))))
        .scalars()
        .all()
    }

    # One roster-slot load serves both the per-side state overlay and the remaining
    # counts, rather than `_per_side_slot_state` plus a `_remaining_count` per side.
    roster_rows = (
        (
            await session.execute(
                select(RosterSlot).where(
                    RosterSlot.team_id.in_(all_team_ids), RosterSlot.week == week
                )
            )
        )
        .scalars()
        .all()
    )
    state = {(r.team_id, r.player_id): (r.game_state, r.is_live) for r in roster_rows}
    remaining_by_team: dict[str, int] = dict.fromkeys(all_team_ids, 0)
    for r in roster_rows:
        if r.slot in STARTER_EXCLUDED_SLOTS:
            continue
        if _slot_is_remaining(r.game_state):
            remaining_by_team[r.team_id] += 1

    entries: list[GameDayMatchup] = []
    for team in user_teams:
        matchup = matchup_by_team.get(team.id)
        if matchup is None:
            continue
        i_am_home = matchup.home_team_id == team.id
        opp_id = matchup.away_team_id if i_am_home else matchup.home_team_id
        opp = teams_by_id.get(opp_id)

        slots = sorted(
            (
                _matchup_slot_schema(
                    row, players, state, matchup.home_team_id, matchup.away_team_id
                )
                for row in slots_by_matchup.get(matchup.id, [])
            ),
            key=lambda sl: _SLOT_RANK.get(sl.slot, len(SLOT_ORDER)),
        )

        entries.append(
            GameDayMatchup(
                team_id=team.id,
                team_name=team.name,
                opp_team_id=opp_id,
                opp_team_name=opp.name if opp is not None else "",
                league_id=team.league_id,
                league_name=league_names.get(team.league_id, ""),
                # `Team` carries no platform field (design D5) — it lives in the id's
                # `{platform}:{platform_id}` prefix, the same split Sidebar.tsx does.
                platform=_split_id(team.id)[0],
                record=schemas.Record(w=team.record_w, l=team.record_l, t=team.record_t),
                rank=schemas.Rank(current=team.rank_current, total=team.rank_total),
                # Scores come from the *week's* matchup row, so a past-week request
                # reports that week's values rather than the current week's.
                score=matchup.home_score if i_am_home else matchup.away_score,
                opp_score=matchup.away_score if i_am_home else matchup.home_score,
                proj=matchup.home_proj if i_am_home else matchup.away_proj,
                opp_proj=matchup.away_proj if i_am_home else matchup.home_proj,
                remaining=Remaining(
                    mine=remaining_by_team.get(team.id, 0),
                    theirs=remaining_by_team.get(opp_id, 0),
                ),
                is_complete=matchup.is_complete,
                i_am_home=i_am_home,
                slots=slots,
            )
        )

    # Stable, human-sensible order for a first render; the client persists its own order
    # on top of this and reconciles against it (design D8).
    entries.sort(key=lambda e: (e.league_name, e.team_name, e.team_id))
    return GameDayData(matchups=entries)


async def _most_started(session: AsyncSession, team_id: str) -> MostStarted | None:
    row = (
        await session.execute(
            select(
                RosterSlot.player_id,
                func.count().label("starts"),
                func.avg(RosterSlot.actual_points).label("avg_points"),
            )
            .where(RosterSlot.team_id == team_id, RosterSlot.slot.not_in(STARTER_EXCLUDED_SLOTS))
            .group_by(RosterSlot.player_id)
            .order_by(func.count().desc(), func.avg(RosterSlot.actual_points).desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    player = await session.get(Player, row.player_id)
    if player is None:
        return None
    return MostStarted(
        player=_player_schema(player),
        starts=int(row.starts),
        avg_points=round(float(row.avg_points or 0.0), 2),
    )


def _longest_win_streak(weeks: list[schemas.SeasonWeek]) -> int:
    best = run = 0
    for w in weeks:
        run = run + 1 if w.is_win else 0
        best = max(best, run)
    return best


async def get_season(session: AsyncSession, team_id: str) -> SeasonData | None:
    """Season detail: every persisted week plus computed highlights. `None` for an unknown
    team id."""
    team_row = await session.get(Team, team_id)
    if team_row is None:
        return None

    week_rows = (
        (
            await session.execute(
                select(SeasonWeek).where(SeasonWeek.team_id == team_id).order_by(SeasonWeek.week)
            )
        )
        .scalars()
        .all()
    )
    weeks = [_season_week_schema(r) for r in week_rows]

    season_high = max(weeks, key=lambda w: w.score, default=None)
    highlights = Highlights(
        season_high=season_high,
        win_streak=_longest_win_streak(weeks),
        most_started=await _most_started(session, team_id),
    )
    return SeasonData(weeks=weeks, highlights=highlights)


def _connection_is_connected(row: Connection | None, platform: str) -> bool:
    if row is None:
        return False
    if platform == "yahoo":
        return row.access_token_enc is not None
    return row.swid_enc is not None and row.espn_s2_enc is not None


async def build_meta(
    session: AsyncSession, next_refresh_at: datetime | None = None
) -> schemas.Meta:
    """Envelope `meta` for every read endpoint (design.md D12).

    - `live_state`: the `services/live_state.py` classifier's most recent verdict, kept
      current by the `refresh_nfl_state` scheduler job (task 8.2/8.5).
    - `as_of`: newest cache-write / refresh-run timestamp (what the data's freshness
      actually reflects), falling back to now on a never-refreshed database.
    - `next_refresh_at`: the scheduler's next planned run when the caller provides it
      (the API layer asks `scheduler.next_run_time()`), else now + the off-day cadence.
    - `platforms`: connection status overlaid with the last refresh error per platform.
    """
    now = datetime.now(UTC).replace(tzinfo=None)

    newest_cache = (await session.execute(select(func.max(HttpCache.fetched_at)))).scalar()
    newest_run = (await session.execute(select(func.max(RefreshRun.run_at)))).scalar()
    as_of = max((ts for ts in (newest_cache, newest_run) if ts is not None), default=now)

    platforms: dict[str, schemas.PlatformStatus] = {}
    for platform in PLATFORMS:
        row = await session.get(Connection, platform)
        if not _connection_is_connected(row, platform):
            platforms[platform] = schemas.PlatformStatus(ok=False, error="not_connected")
            continue
        error = _LAST_ERRORS.get(platform)
        platforms[platform] = schemas.PlatformStatus(ok=error is None, error=error)

    return schemas.Meta(
        live_state=live_state_service.get_current_live_state(),
        as_of=as_of,
        next_refresh_at=next_refresh_at or (now + timedelta(minutes=30)),
        platforms=platforms,
    )


# --------------------------------------------------------------------------------------
# Discovery (the write path — scheduler / manual refresh only)
# --------------------------------------------------------------------------------------


def _current_season(now: datetime | None = None) -> int:
    """NFL season year heuristic: the season that starts in September carries that
    calendar year's label through the Super Bowl the following February."""
    now = now or datetime.now(UTC)
    return now.year if now.month >= 8 else now.year - 1


def _split_id(internal_id: str) -> tuple[str, str]:
    platform, platform_id = internal_id.split(":", 1)
    return platform, platform_id


async def _upsert_league(session: AsyncSession, league: schemas.League) -> None:
    await session.merge(
        League(
            id=league.id,
            platform=league.platform,
            platform_id=league.platform_id,
            name=league.name,
            season=league.season,
            team_count=league.team_count,
            scoring_type=league.scoring_type,
            current_week=league.current_week,
        )
    )


async def _upsert_team(session: AsyncSession, team: schemas.Team) -> None:
    platform, platform_id = _split_id(team.id)
    await session.merge(
        Team(
            id=team.id,
            league_id=team.league_id,
            platform=platform,
            platform_id=platform_id,
            name=team.name,
            manager_name=team.manager_name,
            record_w=team.record.w,
            record_l=team.record.l,
            record_t=team.record.t,
            rank_current=team.rank.current,
            rank_total=team.rank.total,
            points_for=team.points_for,
            points_against=team.points_against,
            is_user_team=team.is_user_team,
        )
    )


async def _upsert_player(session: AsyncSession, player: schemas.Player) -> None:
    platform, platform_id = _split_id(player.id)
    if platform == "espn" and platform_id.startswith("p-"):
        # espn mapper ids are `espn:p-{numeric}`; the platform's own PK is the numeric part
        # (it's also what the headshot CDN URL needs).
        platform_id = platform_id[2:]
    await session.merge(
        Player(
            id=player.id,
            platform=platform,
            platform_id=platform_id,
            name=player.name,
            position=player.position,
            nfl_team=player.nfl_team,
            nfl_opponent=player.nfl_opponent,
            nfl_game_id=player.nfl_game_id,
            bye_week=player.bye_week,
            injury_status=player.injury_status,
        )
    )
    if platform == "yahoo" and player.headshot_url.startswith("http"):
        # Yahoo has no deterministic headshot CDN pattern — stash the payload's source URL
        # for services/headshots.py (keyed by the bare player id used in /api/headshots).
        await session.merge(
            Headshot(
                platform="yahoo",
                player_id=platform_id.rsplit(".", 1)[-1],
                source_url=player.headshot_url,
            )
        )


async def _replace_roster(
    session: AsyncSession, team_id: str, week: int, slots: list[schemas.RosterSlot]
) -> None:
    for slot in slots:
        await _upsert_player(session, slot.player)
    await session.execute(
        delete(RosterSlot).where(RosterSlot.team_id == team_id, RosterSlot.week == week)
    )
    for slot in slots:
        session.add(
            RosterSlot(
                team_id=slot.team_id,
                week=slot.week,
                slot=slot.slot,
                player_id=slot.player.id,
                proj_points=slot.proj_points,
                actual_points=slot.actual_points,
                is_live=slot.is_live,
                game_state=slot.game_state,
                status_text=slot.status_text,
            )
        )


async def _upsert_player_pool_entries(
    session: AsyncSession, league_id: str, entries: list[schemas.PlayerPoolEntry]
) -> None:
    """Replace one league's pool wholesale, the same shape as `_replace_roster`.

    Replace rather than merge because the pool is an authoritative snapshot: a player
    claimed since the last sync has to *disappear*, and a merge would leave the stale
    `FREEAGENT` row behind, offering the user a waiver claim on someone already
    rostered.
    """
    for entry in entries:
        await _upsert_player(session, entry.player)

    await session.execute(delete(PlayerPoolEntry).where(PlayerPoolEntry.league_id == league_id))
    for entry in entries:
        session.add(
            PlayerPoolEntry(
                league_id=league_id,
                player_id=entry.player.id,
                status=entry.status,
                on_team_id=entry.on_team_id,
                percent_owned=entry.percent_owned,
                percent_started=entry.percent_started,
                season_proj_points=entry.season_proj_points,
                eligible_slots=json.dumps(entry.eligible_slots),
            )
        )


async def _upsert_matchup(session: AsyncSession, matchup: schemas.Matchup) -> None:
    await session.merge(
        Matchup(
            id=matchup.id,
            league_id=matchup.league_id,
            week=matchup.week,
            home_team_id=matchup.home_team_id,
            away_team_id=matchup.away_team_id,
            home_score=matchup.home_score,
            away_score=matchup.away_score,
            home_proj=matchup.home_proj,
            away_proj=matchup.away_proj,
            is_complete=matchup.is_complete,
        )
    )


async def _replace_matchup_slots(
    session: AsyncSession, matchup_id: str, slots: list[schemas.MatchupSlot]
) -> None:
    await session.execute(delete(MatchupSlot).where(MatchupSlot.matchup_id == matchup_id))
    for slot in slots:
        session.add(
            MatchupSlot(
                matchup_id=matchup_id,
                slot=slot.slot,
                home_player_id=slot.home_player.id,
                away_player_id=slot.away_player.id,
                home_pts=slot.home_pts,
                away_pts=slot.away_pts,
            )
        )


async def _upsert_season_week(
    session: AsyncSession,
    team_id: str,
    week: int,
    score: float,
    opp_score: float,
    opp_team_name: str,
    is_complete: bool,
) -> None:
    row = (
        await session.execute(
            select(SeasonWeek).where(SeasonWeek.team_id == team_id, SeasonWeek.week == week)
        )
    ).scalar_one_or_none()
    if row is None:
        row = SeasonWeek(team_id=team_id, week=week)
        session.add(row)
    row.score = score
    row.opp_score = opp_score
    row.opp_team_name = opp_team_name
    row.is_win = bool(is_complete and score > opp_score)
    row.is_current = True
    # The freshly-synced week is the current one; anything older is history.
    for other in (
        (
            await session.execute(
                select(SeasonWeek).where(SeasonWeek.team_id == team_id, SeasonWeek.week != week)
            )
        )
        .scalars()
        .all()
    ):
        other.is_current = False


async def _record_season_weeks_from_matchup(
    session: AsyncSession, matchup: schemas.Matchup, team_names: dict[str, str]
) -> None:
    await _upsert_season_week(
        session,
        matchup.home_team_id,
        matchup.week,
        matchup.home_score,
        matchup.away_score,
        team_names.get(matchup.away_team_id, ""),
        matchup.is_complete,
    )
    await _upsert_season_week(
        session,
        matchup.away_team_id,
        matchup.week,
        matchup.away_score,
        matchup.home_score,
        team_names.get(matchup.home_team_id, ""),
        matchup.is_complete,
    )


def _pair_matchup_slots(
    matchup: schemas.Matchup,
    home_slots: list[schemas.RosterSlot],
    away_slots: list[schemas.RosterSlot],
) -> list[schemas.MatchupSlot]:
    """Pair two rosters' starters by internal slot label (Yahoo has no boxscore pairing of
    its own; this mirrors what espn.mapper.map_matchup produces natively)."""
    home = {s.slot: s for s in home_slots if s.slot not in STARTER_EXCLUDED_SLOTS}
    away = {s.slot: s for s in away_slots if s.slot not in STARTER_EXCLUDED_SLOTS}
    return [
        schemas.MatchupSlot(
            matchup_id=matchup.id,
            slot=slot,
            home_player=home[slot].player,
            away_player=away[slot].player,
            home_pts=home[slot].actual_points,
            away_pts=away[slot].actual_points,
            # No join needed here: this write path already holds both sides' RosterSlot
            # schemas, which carry game_state/is_live directly. The read path
            # (`_per_side_slot_state`) has to look them up because `matchup_slots`
            # persists only the points.
            home_state=home[slot].game_state,
            away_state=away[slot].game_state,
            home_is_live=home[slot].is_live,
            away_is_live=away[slot].is_live,
        )
        for slot in sorted(set(home) & set(away), key=lambda s: _SLOT_RANK.get(s, len(SLOT_ORDER)))
    ]


async def _discover_yahoo(factory: async_sessionmaker, settings: Settings) -> None:
    async with factory() as session:
        conn = await session.get(Connection, "yahoo")
        if conn is None or not conn.access_token_enc or not conn.refresh_token_enc:
            return
        access_token = credentials.decrypt(settings.gridiron_secret_key, conn.access_token_enc)
        refresh_token = credentials.decrypt(settings.gridiron_secret_key, conn.refresh_token_enc)

    async def persist_tokens(new_access: str, new_refresh: str) -> None:
        async with factory() as s:
            row = await s.get(Connection, "yahoo")
            if row is not None:
                row.access_token_enc = credentials.encrypt(settings.gridiron_secret_key, new_access)
                row.refresh_token_enc = credentials.encrypt(
                    settings.gridiron_secret_key, new_refresh
                )
                await s.commit()

    client = YahooClient(settings, access_token, refresh_token, on_token_refresh=persist_tokens)
    try:
        async with factory() as session:
            game_key = await client.resolve_game_key(session)
            league_items = await client.list_leagues_raw(session, game_key)

        # Phase 8: skip leagues with is_enabled=False — a disabled league's row/teams stay
        # in the DB (list_teams already filters it out of the aggregation), so this is a
        # bandwidth optimization: don't spend a live-tier tick's HTTP budget re-fetching
        # rosters/matchups nobody can see.
        for league_item in league_items:
            league = yahoo_mapper.map_league(league_item)
            week = league.current_week

            async with factory() as session:
                existing_league = await session.get(League, league.id)
            if existing_league is not None and not existing_league.is_enabled:
                continue

            async with factory() as session:
                await _upsert_league(session, league)

                team_items = await client.list_teams_raw(session, league.platform_id)
                teams = [yahoo_mapper.map_team(item, league.id) for item in team_items]
                for team in teams:
                    team = team.model_copy(
                        update={"rank": schemas.Rank(current=team.rank.current, total=len(teams))}
                    )
                    await _upsert_team(session, team)

                user_team = next((t for t in teams if t.is_user_team), None)
                if user_team is None:
                    await session.commit()
                    continue
                user_key = _split_id(user_team.id)[1]

                # `current_week=week` here always equals `week` today (discovery only ever
                # syncs a league's own current week) so this never actually selects the
                # past-week TTL branch (services/cache.py:select_ttl, task 9.5) — the
                # parameter exists so a future backfill-a-past-week caller can pass a
                # `week` behind the league's `current_week` and get the long TTL for free.
                # Phase 8: SSE `data.changed` events must never fire for past weeks.
                roster_raw = await client.get_roster(session, user_key, week, current_week=week)
                user_slots = yahoo_mapper.map_roster(roster_raw, week)
                await _replace_roster(session, user_team.id, week, user_slots)

                matchup_raw = await client.get_matchup(session, user_key, week, current_week=week)
                matchup = yahoo_mapper.map_matchup(matchup_raw, week)
                await _upsert_matchup(session, matchup)

                opp_id = (
                    matchup.away_team_id
                    if matchup.home_team_id == user_team.id
                    else matchup.home_team_id
                )
                opp_key = _split_id(opp_id)[1]
                opp_raw = await client.get_roster(session, opp_key, week, current_week=week)
                opp_slots = yahoo_mapper.map_roster(opp_raw, week)
                await _replace_roster(session, opp_id, week, opp_slots)

                if matchup.home_team_id == user_team.id:
                    slots = _pair_matchup_slots(matchup, user_slots, opp_slots)
                else:
                    slots = _pair_matchup_slots(matchup, opp_slots, user_slots)
                await _replace_matchup_slots(session, matchup.id, slots)

                await _record_season_weeks_from_matchup(
                    session, matchup, {t.id: t.name for t in teams}
                )
                await session.commit()
    finally:
        await client.aclose()


async def _discover_espn(factory: async_sessionmaker, settings: Settings) -> None:
    async with factory() as session:
        conn = await session.get(Connection, "espn")
        if conn is None or not conn.swid_enc or not conn.espn_s2_enc:
            return
        swid = credentials.decrypt(settings.gridiron_secret_key, conn.swid_enc)
        espn_s2 = credentials.decrypt(settings.gridiron_secret_key, conn.espn_s2_enc)

        # League ids to sync: everything already persisted for espn (rows arrive via prior
        # discovery runs or, later, via Settings) plus whatever the credential probe finds.
        league_rows = (
            (await session.execute(select(League).where(League.platform == "espn"))).scalars().all()
        )
    seasons: dict[int, int] = {int(r.platform_id): r.season for r in league_rows}
    league_ids = set(seasons)

    client = EspnClient(settings, swid=swid, espn_s2=espn_s2, session_factory=factory)
    try:
        probe_year = _current_season()
        try:
            for league_id in await client.discover_leagues(probe_year):
                league_ids.add(league_id)
                seasons.setdefault(league_id, probe_year)
        except (httpx.HTTPStatusError, ValueError):
            pass  # discovery is best-effort; sync continues with already-known leagues

        # Phase 8: skip leagues with is_enabled=False (see the matching comment in
        # _discover_yahoo — same bandwidth-optimization seam). Checked against the
        # internal id directly, before the upstream `get_league` call, so a disabled
        # league costs nothing beyond one local SELECT.
        for league_id in sorted(league_ids):
            async with factory() as session:
                existing_league = await session.get(League, f"espn:{league_id}")
            if existing_league is not None and not existing_league.is_enabled:
                continue

            year = seasons.get(league_id, probe_year)
            raw = await client.get_league(league_id, year)
            league = espn_mapper.map_league(raw)
            week = league.current_week
            user_team_id = espn_mapper.resolve_user_team_id(raw, swid)

            async with factory() as session:
                await _upsert_league(session, league)
                for team_raw in raw.get("teams", []):
                    team = espn_mapper.map_team(team_raw, league.platform_id)
                    team = team.model_copy(
                        update={
                            "manager_name": espn_mapper.manager_name_for(raw, team_raw["id"]),
                            "is_user_team": team_raw["id"] == user_team_id,
                            "rank": schemas.Rank(
                                current=team.rank.current, total=league.team_count
                            ),
                        }
                    )
                    await _upsert_team(session, team)
                await session.commit()

            # See the matching comment in _discover_yahoo: `current_week=week` is always
            # equal to `week` on this call path, so services/cache.py:select_ttl's
            # past-week branch (task 9.5) stays dormant here — it's wired for a future
            # backfill-a-past-week caller. Phase 8: SSE `data.changed` events must never
            # fire for past weeks.
            roster_raw = await client.get_roster(league_id, year, week, current_week=week)
            all_slots = espn_mapper.map_roster(roster_raw, week)

            async with factory() as session:
                by_team: dict[str, list[schemas.RosterSlot]] = {}
                for slot in all_slots:
                    by_team.setdefault(slot.team_id, []).append(slot)
                for team_id, slots in by_team.items():
                    await _replace_roster(session, team_id, week, slots)

                if user_team_id is not None:
                    matchup, matchup_slots = espn_mapper.map_matchup(roster_raw, week, user_team_id)
                    await _upsert_matchup(session, matchup)
                    await _replace_matchup_slots(session, matchup.id, matchup_slots)
                    names = {
                        f"espn:l-{league.platform_id}-t-{t['id']}": (
                            t.get("name")
                            or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
                        )
                        for t in raw.get("teams", [])
                    }
                    await _record_season_weeks_from_matchup(session, matchup, names)
                await session.commit()
    finally:
        await client.aclose()


def _classify_error(exc: BaseException) -> str:
    if isinstance(exc, AuthRequiredError):
        return "auth_required"
    if isinstance(exc, RateLimitedError):
        return "rate_limited"
    if isinstance(exc, CredentialDecryptError):
        return "credential_decrypt_error"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"upstream_error ({exc.response.status_code})"
    if isinstance(exc, httpx.HTTPError):
        return "upstream_unreachable"
    return f"{type(exc).__name__}: {exc}"


def _needs_cooldown(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitedError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


async def refresh_discovery(
    session: AsyncSession, settings: Settings | None = None
) -> dict[str, PlatformOutcome]:
    """Discover leagues + teams (+ current-week rosters/matchups) for every connected
    platform and upsert the normalized rows.

    Per-platform failures are isolated (`asyncio.gather(return_exceptions=True)`) and
    recorded — in the returned outcomes, in `_LAST_ERRORS` (surfaced by `build_meta`), and
    as a rate-limit/5xx cooldown — never raised. Each platform runs on its own DB sessions
    (an `AsyncSession` is not safe for concurrent use); `session` supplies the bind so
    tests can point everything at a temp database.
    """
    settings = settings or get_settings()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)

    now = datetime.now(UTC)
    outcomes: dict[str, PlatformOutcome] = {}
    tasks: dict[str, object] = {}
    for platform, coro_fn in (("yahoo", _discover_yahoo), ("espn", _discover_espn)):
        cooldown_until = _COOLDOWN_UNTIL.get(platform)
        if cooldown_until is not None and now < cooldown_until:
            outcomes[platform] = PlatformOutcome(
                ok=False, error=f"cooldown until {cooldown_until.isoformat()}"
            )
            _LAST_ERRORS[platform] = outcomes[platform].error
            continue
        tasks[platform] = coro_fn(factory, settings)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for platform, result in zip(tasks.keys(), results):
        if isinstance(result, BaseException):
            error = _classify_error(result)
            logger.warning("discovery failed for %s: %s", platform, error)
            if _needs_cooldown(result):
                set_cooldown(platform, now + COOLDOWN)
            outcomes[platform] = PlatformOutcome(ok=False, error=error)
            _LAST_ERRORS[platform] = error
        else:
            outcomes[platform] = PlatformOutcome(ok=True)
            _LAST_ERRORS[platform] = None
            _COOLDOWN_UNTIL.pop(platform, None)
    return outcomes


def summarize_outcomes(outcomes: dict[str, PlatformOutcome]) -> str | None:
    """One-line error summary for `refresh_runs.error`, or `None` when every platform
    succeeded (or was simply not connected)."""
    errors = [f"{p}: {o.error}" for p, o in outcomes.items() if not o.ok]
    return "; ".join(errors) if errors else None


async def refresh_player_pool(
    session: AsyncSession, settings: Settings | None = None
) -> str | None:
    """Refresh the free-agent/waiver/rostered pool for every league the user plays in.

    Return value follows the `JOBS` protocol: `None` means success, and any string is
    recorded as `refresh_runs.error` with `ok=False`. That is why a clean run returns
    `None` rather than a count — a summary string would mark every successful run as
    failed. The per-league totals are logged instead.

    A nonzero skip count IS returned, and so does mark the run not-ok. That is
    deliberate: a live pull across two leagues mapped 2002 entries with zero skips, so
    skips are not a normal operating condition — they mean ESPN introduced a position
    or slot this app cannot read, and that should be visible in Settings' "last
    refresh" line rather than buried. The sync still persists everything it could
    (design D6); "not ok" here means "degraded", not "aborted".
    """
    settings = settings or get_settings()

    conn = await session.get(Connection, "espn")
    if conn is None or not conn.swid_enc or not conn.espn_s2_enc:
        return None  # ESPN not connected — nothing to do, and not an error

    swid = credentials.decrypt(settings.gridiron_secret_key, conn.swid_enc)
    espn_s2 = credentials.decrypt(settings.gridiron_secret_key, conn.espn_s2_enc)

    # Only leagues the user actually plays in. The ownership column is `is_user_team`.
    league_rows = (
        (
            await session.execute(
                select(League)
                .join(Team, Team.league_id == League.id)
                .where(
                    League.platform == "espn",
                    League.is_enabled.is_(True),
                    Team.is_user_team.is_(True),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if not league_rows:
        return None

    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    client = EspnClient(settings, swid=swid, espn_s2=espn_s2, session_factory=factory)

    total_entries = 0
    total_skipped = 0
    synced = 0
    fresh = 0
    errors: list[str] = []

    try:
        for league in league_rows:
            # The freshness marker is written when the fetch succeeds, but the rows are
            # persisted afterwards — so anything that interrupts the gap (a crash, a DB
            # error, a caller that fetched without persisting) leaves a fresh marker
            # over an empty pool, and the league would then be skipped for a full TTL.
            # Checking what is actually persisted makes the job self-healing.
            persisted = await session.scalar(
                select(func.count())
                .select_from(PlayerPoolEntry)
                .where(PlayerPoolEntry.league_id == league.id)
            )

            try:
                raw = await client.get_player_pool(
                    int(league.platform_id), league.season, force=not persisted
                )
            except (httpx.HTTPStatusError, httpx.HTTPError, AuthRequiredError) as exc:
                errors.append(f"{league.name}: {_classify_error(exc)}")
                continue

            if raw is None:
                # Still within PLAYER_POOL_TTL — the persisted pool is current, and the
                # body was not retained to hand back (design D4).
                fresh += 1
                continue

            entries, skipped = espn_mapper.map_player_pool(raw, season=league.season)
            async with factory() as write_session:
                await _upsert_player_pool_entries(write_session, league.id, entries)
                await write_session.commit()

            total_entries += len(entries)
            total_skipped += skipped
            synced += 1
    finally:
        await client.aclose()

    logger.info(
        "player_pool: %d leagues synced (%d already fresh), %d entries, %d skipped",
        synced,
        fresh,
        total_entries,
        total_skipped,
    )

    if errors:
        return "; ".join(errors)
    if total_skipped:
        return f"skipped {total_skipped} unmappable entries across {synced} league(s)"
    return None


async def refresh_fantasy(session: AsyncSession, settings: Settings | None = None) -> str | None:
    """Adaptive-cadence refresh (task 8.3): re-syncs every *enabled* league through the
    same `refresh_discovery` machinery `sync_discovery` uses (disabled leagues are now
    skipped inside `_discover_yahoo`/`_discover_espn` — see the `# Phase 8:` seam
    comments there), then diffs the *current* week's read-model against the previous
    run's fingerprints and publishes `data.changed` for whatever changed.

    Phase 8: SSE `data.changed` events must never fire for past weeks — the only week
    ever diffed here is `current_week(session)`.

    While `live_state` is "live", the roster/matchup HTTP cache's normal TTL
    (`platforms/espn/client.py`'s `ROSTER_TTL` = 1h, tuned for the off-day default) would
    otherwise make a 10-30s live-tier poll a no-op — it'd keep re-reading the same cached
    payload until the TTL expires, so fingerprints would never move and no `data.changed`
    would ever fire during a live game. `cache.invalidate` (its own docstring calls out
    exactly this "Live-game invalidation" scenario) forces the very next fetch past the
    cache for both platforms, so a live-tier tick always sees fresh upstream data.
    """
    if live_state_service.get_current_live_state() == "live":
        await cache_service.invalidate(session, platform="yahoo")
        await cache_service.invalidate(session, platform="espn")

    outcomes = await refresh_discovery(session, settings)

    week = await current_week(session)
    fingerprints = await differ.fantasy_fingerprints(session, week)
    differ.diff_and_publish(fingerprints)

    return summarize_outcomes(outcomes)
