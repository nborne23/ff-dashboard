"""Every head-to-head pairing in a league, not just the user's — the All Matchups screen.

Same split as `fantasy_service` (design.md D7):

- **Writes** run inside discovery. ESPN's roster+matchup payload already carries the
  whole league's schedule, so its pairings cost no extra request
  (`store_espn_league_matchups`). Yahoo needs one `/scoreboard` request per league per
  week (`sync_yahoo_league_matchups`), made after the user's own data is committed so a
  failure here never costs a tick its core data.
- **Reads** (`get_league_matchups`, `get_league_matchup_detail`) only assemble persisted
  rows.

Past weeks are backfilled insert-only and only while no game is live: `refresh_fantasy`
wipes the whole HTTP cache on every live tick, so a past-week fetch made then could not
lean on its 24h cache entry, and a row already on disk (the user's own, written when that
week was current) is better data than a schedule-derived total.
"""

import logging

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron import schemas
from backend.gridiron.errors import AuthRequiredError, CredentialDecryptError, RateLimitedError
from backend.gridiron.models import League, Matchup, MatchupSlot, Player, RosterSlot, Team
from backend.gridiron.platforms.espn import mapper as espn_mapper
from backend.gridiron.platforms.yahoo import mapper as yahoo_mapper
from backend.gridiron.platforms.yahoo.client import YahooClient
from backend.gridiron.services import fantasy_service as fs
from backend.gridiron.services import live_state as live_state_service

logger = logging.getLogger("uvicorn.error")

# Past Yahoo weeks fetched per discovery run. Backfill only runs off-live, when discovery
# is on its slow cadence, so a whole season fills in within a few runs without one run
# spending a dozen requests at once.
YAHOO_BACKFILL_WEEKS_PER_RUN = 2

# `(league_id, week)` pairs already backfilled this process. A week whose scoreboard holds
# fewer pairings than `team_count // 2` (a playoff week, where eliminated teams sit out)
# would otherwise stay "missing" forever and be re-fetched every run ahead of the older
# weeks still waiting. Module-level like `fantasy_service._LAST_ERRORS` — single-process,
# single-user app (design.md D1); a restart retries each week once.
_BACKFILLED_WEEKS: set[tuple[str, int]] = set()


def reset_state() -> None:
    _BACKFILLED_WEEKS.clear()


def _is_live() -> bool:
    return live_state_service.get_current_live_state() == "live"


async def _insert_missing_matchups(
    session: AsyncSession, league_id: str, matchups: list[schemas.Matchup]
) -> int:
    """Add each matchup whose week has no row for either of its teams yet. Never updates:
    an existing row — the user's own, written when that week was current — carries a
    real projection and slots, which a schedule-derived total would overwrite with less.
    """
    if not matchups:
        return 0
    weeks = {m.week for m in matchups}
    taken = {
        (week, team_id)
        for week, home, away in (
            await session.execute(
                select(Matchup.week, Matchup.home_team_id, Matchup.away_team_id).where(
                    Matchup.league_id == league_id, Matchup.week.in_(weeks)
                )
            )
        ).all()
        for team_id in (home, away)
    }
    added = 0
    for m in matchups:
        if (m.week, m.home_team_id) in taken or (m.week, m.away_team_id) in taken:
            continue
        session.add(
            Matchup(
                id=m.id,
                league_id=m.league_id,
                week=m.week,
                home_team_id=m.home_team_id,
                away_team_id=m.away_team_id,
                home_score=m.home_score,
                away_score=m.away_score,
                home_proj=m.home_proj,
                away_proj=m.away_proj,
                is_complete=m.is_complete,
            )
        )
        taken.update({(m.week, m.home_team_id), (m.week, m.away_team_id)})
        added += 1
    return added


def _involves(matchup: schemas.Matchup, team_id: str | None) -> bool:
    return team_id is not None and team_id in (matchup.home_team_id, matchup.away_team_id)


async def store_espn_league_matchups(
    session: AsyncSession, roster_raw: dict, week: int, user_team_id: str | None
) -> None:
    """Persist every other pairing in an ESPN roster+matchup payload, in the caller's
    transaction. The user's own matchup is skipped: discovery's existing path already
    wrote it (and its season-week rows) from the same payload.

    Best-effort: a payload this mapper can't read is logged rather than raised, since an
    exception here would roll back the user's own rows sharing the transaction.
    """
    try:
        mapped = espn_mapper.map_league_matchups(roster_raw, week)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("espn league matchups skipped: %s", exc)
        return

    past: list[schemas.Matchup] = []
    for matchup, slots in mapped:
        if matchup.week == week:
            if _involves(matchup, user_team_id):
                continue
            await fs._upsert_matchup(session, matchup)
            await fs._replace_matchup_slots(session, matchup.id, slots)
        else:
            past.append(matchup)

    if past and not _is_live():
        await _insert_missing_matchups(session, past[0].league_id, past)


async def _yahoo_weeks_to_backfill(
    session: AsyncSession, league_id: str, week: int, team_count: int
) -> list[int]:
    """Past weeks with fewer stored pairings than the league plays, newest first."""
    expected = max(team_count // 2, 1)
    counts: dict[int, int] = {}
    for (w,) in (
        await session.execute(
            select(Matchup.week).where(Matchup.league_id == league_id, Matchup.week < week)
        )
    ).all():
        counts[w] = counts.get(w, 0) + 1
    return [
        w
        for w in range(week - 1, 0, -1)
        if counts.get(w, 0) < expected and (league_id, w) not in _BACKFILLED_WEEKS
    ]


async def sync_yahoo_league_matchups(
    factory: async_sessionmaker,
    client: YahooClient,
    league: schemas.League,
    user_team_id: str,
) -> None:
    """One `/scoreboard` request for the league's current week (every tick, so other
    matchups' totals stay live), plus — off-live only — up to
    `YAHOO_BACKFILL_WEEKS_PER_RUN` past weeks the DB is still missing pairings for.

    Scoreboard rows involving the user's team are skipped for the current week: the
    team's own `/matchups` path owns that row under its legacy id, and `_upsert_matchup`
    would prune it (slots and all) in favor of the scoreboard's id for the same pairing.
    """
    league_key = league.platform_id
    week = league.current_week
    try:
        async with factory() as session:
            raw = await client.get_scoreboard(session, league_key, week, current_week=week)
            for matchup in yahoo_mapper.map_scoreboard(raw, week):
                if not _involves(matchup, user_team_id):
                    await fs._upsert_matchup(session, matchup)
            await session.commit()

        if _is_live():
            return

        async with factory() as session:
            backfill = await _yahoo_weeks_to_backfill(session, league.id, week, league.team_count)
        for past_week in backfill[:YAHOO_BACKFILL_WEEKS_PER_RUN]:
            async with factory() as session:
                raw = await client.get_scoreboard(session, league_key, past_week, current_week=week)
                await _insert_missing_matchups(
                    session, league.id, yahoo_mapper.map_scoreboard(raw, past_week)
                )
                await session.commit()
            _BACKFILLED_WEEKS.add((league.id, past_week))
    # Same error policy as `fantasy_service._sync_other_yahoo_rosters`: what the
    # platform's cooldown logic has to see propagates, anything else is logged.
    except (AuthRequiredError, RateLimitedError, CredentialDecryptError):
        raise
    except httpx.HTTPStatusError as exc:
        if fs._needs_cooldown(exc) or exc.response.status_code in (401, 403, 429):
            raise
        logger.warning("yahoo league matchups for %s skipped: %s", league.id, exc)
    except (httpx.HTTPError, yahoo_mapper.MapperError, KeyError, ValueError) as exc:
        logger.warning("yahoo league matchups for %s skipped: %s", league.id, exc)


# --- Reads ---------------------------------------------------------------------------


class LeagueMatchupSide(BaseModel):
    team: schemas.Team
    # The standings position the League screen shows — not `team.rank.current`, which
    # is the platform's playoff seed and is 0 for every team in some leagues.
    position: int
    # Starters whose NFL game isn't final yet (same rule as Head-to-Head's count).
    remaining: int
    # Any starter's NFL game in progress right now.
    is_live: bool


class LeagueMatchupEntry(BaseModel):
    matchup: schemas.Matchup
    home: LeagueMatchupSide
    away: LeagueMatchupSide
    is_user_matchup: bool


class LeagueMatchupsData(BaseModel):
    league: schemas.League
    week: int
    matchups: list[LeagueMatchupEntry]


class LeagueMatchupDetail(BaseModel):
    league: schemas.League
    week: int
    matchup: schemas.Matchup
    home: LeagueMatchupSide
    away: LeagueMatchupSide
    is_user_matchup: bool
    slots: list[schemas.MatchupSlot]


def _lite_team(row: Team) -> schemas.Team:
    """The league-wide team shape `get_league_standings` builds: the week-scoped fields
    `_team_schema` computes would cost a handful of queries per team, and the matchup
    row already carries the week's score."""
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
        current_score=0.0,
        current_opp_score=0.0,
        current_opponent_name="",
        is_live=False,
        spark_last_6=[],
        accent_color=fs.ACCENT_COLOR,
        logo_url=fs._team_logo_url(row.platform, row.platform_id, row.logo_source_url),
    )


async def _league_context(
    session: AsyncSession, team_id: str
) -> tuple[League, dict[str, Team], dict[str, int]] | None:
    """`(league row, team rows by id, standings position by team id)` for the league
    `team_id` plays in, or `None` for an unknown team."""
    team_row = await session.get(Team, team_id)
    if team_row is None:
        return None
    league_row = await session.get(League, team_row.league_id)
    if league_row is None:
        return None
    rows = (
        (await session.execute(select(Team).where(Team.league_id == team_row.league_id)))
        .scalars()
        .all()
    )
    ordered = sorted(rows, key=fs._standings_sort_key)
    return league_row, {r.id: r for r in rows}, {r.id: i + 1 for i, r in enumerate(ordered)}


async def _starter_states(
    session: AsyncSession, team_ids: list[str], week: int
) -> tuple[list[tuple[RosterSlot, Player, str | None]], dict[str, int], dict[str, bool]]:
    """Every week-`week` roster row for `team_ids` with its resolved game state, plus
    per-team starters-remaining and any-starter-live. One roster query for all of it —
    `fantasy_service._slot_state_and_remaining` resolves the same states but can't say
    which belong to starters, which "live" needs."""
    if not team_ids:
        return [], {}, {}
    states, fallback = await fs._nfl_states_for_week(session, week)
    rows = (
        await session.execute(
            select(RosterSlot, Player)
            .join(Player, RosterSlot.player_id == Player.id)
            .where(RosterSlot.team_id.in_(team_ids), RosterSlot.week == week)
        )
    ).all()
    resolved_rows: list[tuple[RosterSlot, Player, str | None]] = []
    remaining = dict.fromkeys(team_ids, 0)
    live = dict.fromkeys(team_ids, False)
    for row, player in rows:
        state = fs._resolve_slot_state(row.game_state, player, week, states, fallback)
        resolved_rows.append((row, player, state))
        if row.slot in fs.STARTER_EXCLUDED_SLOTS:
            continue
        if fs._slot_is_remaining(state):
            remaining[row.team_id] = remaining.get(row.team_id, 0) + 1
        if state == "in":
            live[row.team_id] = True
    return resolved_rows, remaining, live


def _side(
    team: Team, positions: dict[str, int], remaining: dict[str, int], live: dict[str, bool]
) -> LeagueMatchupSide:
    return LeagueMatchupSide(
        team=_lite_team(team),
        position=positions.get(team.id, 0),
        remaining=remaining.get(team.id, 0),
        is_live=live.get(team.id, False),
    )


async def get_league_matchups(
    session: AsyncSession, team_id: str, week: int
) -> LeagueMatchupsData | None:
    """Every week-`week` pairing in `team_id`'s league. The user's own matchup comes
    first, then the rest by their better-placed team, so the order matches the standings
    the user already knows rather than the platform's arbitrary schedule ids. `None` for
    an unknown team (the API layer 404s); an empty list for a week nothing is stored for.
    """
    context = await _league_context(session, team_id)
    if context is None:
        return None
    league_row, teams, positions = context

    rows = [
        m
        for m in (
            await session.execute(
                select(Matchup).where(Matchup.league_id == league_row.id, Matchup.week == week)
            )
        )
        .scalars()
        .all()
        # A row whose team was since removed from the league can't be drawn.
        if m.home_team_id in teams and m.away_team_id in teams
    ]
    side_ids = sorted({m.home_team_id for m in rows} | {m.away_team_id for m in rows})
    _, remaining, live = await _starter_states(session, side_ids, week)

    entries = [
        LeagueMatchupEntry(
            matchup=fs._matchup_schema(m),
            home=_side(teams[m.home_team_id], positions, remaining, live),
            away=_side(teams[m.away_team_id], positions, remaining, live),
            is_user_matchup=teams[m.home_team_id].is_user_team
            or teams[m.away_team_id].is_user_team,
        )
        for m in rows
    ]
    entries.sort(
        key=lambda e: (
            not e.is_user_matchup,
            min(e.home.position or 999, e.away.position or 999),
            e.matchup.id,
        )
    )
    return LeagueMatchupsData(league=fs._league_schema(league_row), week=week, matchups=entries)


def _paired_from_rosters(
    matchup: Matchup, resolved_rows: list[tuple[RosterSlot, Player, str | None]]
) -> list[schemas.MatchupSlot]:
    """Starter pairings rebuilt from the two teams' stored rosters, for a matchup with
    no `matchup_slots` of its own (a Yahoo pairing other than the user's, or a past week
    backfilled from totals). Goes through `_pair_matchup_slots`, the Yahoo write path's
    own pairing, so the two can't disagree about which slots line up."""
    by_team: dict[str, list[schemas.RosterSlot]] = {}
    for row, player, state in resolved_rows:
        by_team.setdefault(row.team_id, []).append(
            fs._roster_slot_schema(row, player, game_state=state, is_live=state == "in")
        )
    return fs._pair_matchup_slots(
        fs._matchup_schema(matchup),
        by_team.get(matchup.home_team_id, []),
        by_team.get(matchup.away_team_id, []),
    )


async def get_league_matchup_detail(
    session: AsyncSession, team_id: str, matchup_id: str
) -> LeagueMatchupDetail | None:
    """One pairing in `team_id`'s league, with its starter slots, for the read-only
    head-to-head view. `None` when the team is unknown or the matchup isn't in its
    league — `team_id` scopes the lookup, so a URL can't reach another league's row.
    """
    context = await _league_context(session, team_id)
    if context is None:
        return None
    league_row, teams, positions = context

    matchup_row = await session.get(Matchup, matchup_id)
    if (
        matchup_row is None
        or matchup_row.league_id != league_row.id
        or matchup_row.home_team_id not in teams
        or matchup_row.away_team_id not in teams
    ):
        return None

    week = matchup_row.week
    sides = [matchup_row.home_team_id, matchup_row.away_team_id]
    resolved_rows, remaining, live = await _starter_states(session, sides, week)

    slot_rows = (
        (await session.execute(select(MatchupSlot).where(MatchupSlot.matchup_id == matchup_id)))
        .scalars()
        .all()
    )
    if slot_rows:
        player_ids = {s.home_player_id for s in slot_rows} | {s.away_player_id for s in slot_rows}
        players = {
            p.id: p
            for p in (await session.execute(select(Player).where(Player.id.in_(player_ids))))
            .scalars()
            .all()
        }
        state = {
            (row.team_id, row.player_id): (resolved, resolved == "in")
            for row, _, resolved in resolved_rows
        }
        slots = [
            fs._matchup_slot_schema(s, players, state, *sides)
            for s in slot_rows
            if s.home_player_id in players and s.away_player_id in players
        ]
    else:
        slots = _paired_from_rosters(matchup_row, resolved_rows)
    slots.sort(key=lambda s: fs._SLOT_RANK.get(s.slot, len(fs.SLOT_ORDER)))

    home, away = teams[matchup_row.home_team_id], teams[matchup_row.away_team_id]
    return LeagueMatchupDetail(
        league=fs._league_schema(league_row),
        week=week,
        matchup=fs._matchup_schema(matchup_row),
        home=_side(home, positions, remaining, live),
        away=_side(away, positions, remaining, live),
        is_user_matchup=home.is_user_team or away.is_user_team,
        slots=slots,
    )
