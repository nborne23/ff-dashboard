"""Read side of add-nfl-scores: a week of NFL games, and one game's fantasy points.

Everything here reads stored rows (design.md D7):

- the week's trimmed ESPN scoreboard and Sleeper's all-player projections, both from
  `http_cache` via `services/nfl_week_cache.py`;
- `player_weekly_stats` for the stat lines, kept live by `refresh_player_stats`;
- `roster_slots` for the selected league's own numbers.

**Whose points.** A player rostered in the selected league this week shows that league's
own `actual_points` / `proj_points` — the number the user's matchup actually counts.
Everyone else shows Sleeper's line in the league's format (`League.scoring_type`); a
`custom` league falls back to PPR and the response says so. Per-league scoring rules
aren't stored, so a league's bonuses only reach players someone in it rosters.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import League, Player, PlayerWeeklyStat, RosterSlot, Team
from backend.gridiron.schemas.scores import (
    FantasyGroup,
    FantasyPlayer,
    FantasyPosition,
    GameDetail,
    GameLeader,
    ScoreGame,
    ScoresWeek,
    ScoreTeam,
    ScoringLeague,
    StatToken,
)
from backend.gridiron.services import nfl_week_cache
from backend.gridiron.services.fantasy_service import _player_schema
from backend.gridiron.services.player_stats import resolve_format

WEEKS = list(range(1, nfl_week_cache.MAX_WEEK + 1))

POSITIONS: tuple[FantasyPosition, ...] = ("QB", "RB", "WR", "TE", "K", "DEF")

_FORMAT_KEY = {"ppr": "pts_ppr", "half_ppr": "pts_half_ppr", "standard": "pts_std"}

# A player projected under this is a depth-chart body, not someone to list before kickoff.
MIN_LISTED_PROJECTION = 0.1


# --------------------------------------------------------------------------------------
# Scoreboard
# --------------------------------------------------------------------------------------


def _utc(value: str | datetime) -> datetime:
    """ESPN dates look like `2026-11-01T18:00Z`. Sent tz-aware so the client's `Date` reads
    them as UTC rather than as local time."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def period_label(period: int | None) -> str:
    if not period:
        return ""
    if period <= 4:
        return f"Q{period}"
    return "OT" if period == 5 else f"{period - 4}OT"


def status_text(event: dict) -> str:
    state = event.get("state")
    period = event.get("period")
    if state == "post":
        return "Final/OT" if (period or 0) > 4 else "Final"
    if state == "postponed":
        return "Postponed"
    if state == "in":
        name = event.get("status_name")
        if name == "STATUS_HALFTIME":
            return "Half"
        label = period_label(period)
        if name == "STATUS_END_PERIOD":
            return f"End {label}"
        clock = event.get("clock")
        return f"{label} {clock}".strip() if clock else label
    return event.get("short_detail") or ""


def _team(side: dict, state: str) -> ScoreTeam:
    return ScoreTeam(
        abbr=side["abbr"],
        name=side["name"],
        location=side["location"],
        record=side.get("record"),
        score=None if state == "pre" else side.get("score"),
        logo=side.get("logo"),
        color=side.get("color"),
        linescores=side.get("linescores") or [],
        winner=bool(side.get("winner")) and state == "post",
    )


_LEADER_ORDER = ("passing", "rushing", "receiving")


def top_performer(event: dict) -> GameLeader | None:
    """ESPN's passing leader (else rushing, else receiving) — the line Sleeper's scoreboard
    shows under each game. None before kickoff, when ESPN's leaders are season numbers."""
    if event.get("state") not in ("in", "post"):
        return None
    leaders = {leader["category"]: leader for leader in event.get("leaders") or []}
    for category in _LEADER_ORDER:
        leader = leaders.get(category)
        if leader is None or not leader.get("name"):
            continue
        athlete_id = leader.get("athlete_id") or ""
        return GameLeader(
            category=category,  # type: ignore[arg-type]
            name=leader["name"],
            short_name=leader.get("short_name") or leader["name"],
            position=leader.get("position"),
            team=leader.get("team") or "",
            headshot_url=f"/api/headshots/espn/{athlete_id}.png" if athlete_id.isdigit() else None,
            stat_line=leader.get("display_value") or "",
        )
    return None


def score_game(event: dict) -> ScoreGame:
    state = event["state"]
    situation = event.get("situation") or {}
    live = state == "in"
    return ScoreGame(
        game_id=event["id"],
        kickoff_at=_utc(event["kickoff_at"]),
        state=state,
        status_text=status_text(event),
        period=event.get("period") if live else None,
        clock=event.get("clock") if live else None,
        broadcast=event.get("broadcast"),
        possession=situation.get("possession") if live else None,
        down_distance=situation.get("down_distance") if live else None,
        away=_team(event["away"], state),
        home=_team(event["home"], state),
        top_performer=top_performer(event),
    )


async def _season_and_current(session: AsyncSession) -> tuple[int | None, int | None]:
    current = await nfl_week_cache.read_current(session)
    return current if current is not None else (None, None)


async def week_scores(session: AsyncSession, week: int | None) -> ScoresWeek:
    season, current_week = await _season_and_current(session)
    week = week or current_week or 1
    cached = await nfl_week_cache.read_week(session, season, week) if season else None
    if cached is None:
        return ScoresWeek(
            season=season,
            week=week,
            current_week=current_week,
            weeks=WEEKS,
            byes=[],
            fetched_at=None,
            games=[],
        )
    payload, fetched_at = cached
    games = sorted(
        (score_game(e) for e in payload.get("events") or []),
        key=lambda g: (g.kickoff_at, g.game_id),
    )
    return ScoresWeek(
        season=season,
        week=week,
        current_week=current_week,
        weeks=WEEKS,
        byes=payload.get("byes") or [],
        fetched_at=_utc(fetched_at),
        games=games,
    )


async def find_game(
    session: AsyncSession, game_id: str, week: int | None = None
) -> tuple[int, int, dict] | None:
    """`(season, week, event)` for an ESPN game id. Looks in `week` first when the client
    knows it, then the current week, then the rest of the season."""
    season, current_week = await _season_and_current(session)
    if season is None:
        return None
    order = [w for w in (week, current_week) if w] + WEEKS
    seen: set[int] = set()
    for candidate in order:
        if candidate in seen:
            continue
        seen.add(candidate)
        cached = await nfl_week_cache.read_week(session, season, candidate)
        if cached is None:
            continue
        for event in cached[0].get("events") or []:
            if event.get("id") == game_id:
                return season, candidate, event
    return None


# --------------------------------------------------------------------------------------
# Stat lines
# --------------------------------------------------------------------------------------


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _tokens(stats: dict[str, float], position: str) -> list[StatToken]:
    """A Sleeper-style line: `24/31 CMP, 321 YD, 2 TD, 1 INT, 4 CAR, 26 YD`."""
    tokens: list[StatToken] = []

    def add(value: float | str, label: str) -> None:
        tokens.append(
            StatToken(value=value if isinstance(value, str) else _num(value), label=label)
        )

    def get(key: str) -> float:
        return float(stats.get(key) or 0)

    def passing() -> None:
        if get("pass_att"):
            add(f"{_num(get('pass_cmp'))}/{_num(get('pass_att'))}", "CMP")
            add(get("pass_yd"), "YD")
            if get("pass_td"):
                add(get("pass_td"), "TD")
            if get("pass_int"):
                add(get("pass_int"), "INT")

    def rushing() -> None:
        if get("rush_att"):
            add(get("rush_att"), "CAR")
            add(get("rush_yd"), "YD")
            if get("rush_td"):
                add(get("rush_td"), "TD")

    def receiving() -> None:
        if get("rec") or get("rec_tgt"):
            add(
                f"{_num(get('rec'))}/{_num(get('rec_tgt'))}" if get("rec_tgt") else get("rec"),
                "REC",
            )
            add(get("rec_yd"), "YD")
            if get("rec_td"):
                add(get("rec_td"), "TD")

    if position == "QB":
        passing()
        rushing()
        receiving()
    elif position == "RB":
        rushing()
        receiving()
    elif position in ("WR", "TE"):
        receiving()
        rushing()
    elif position == "K":
        if get("fga"):
            add(f"{_num(get('fgm'))}/{_num(get('fga'))}", "FG")
        if get("xpa"):
            add(f"{_num(get('xpm'))}/{_num(get('xpa'))}", "XP")
        if get("fgm_lng"):
            add(get("fgm_lng"), "LNG")
    elif position == "DEF":
        for key, label in (
            ("sack", "SACK"),
            ("int", "INT"),
            ("fum_rec", "FR"),
            ("td", "TD"),
            ("safe", "SFTY"),
        ):
            if get(key):
                add(get(key), label)
        if "pts_allow" in stats:
            add(get("pts_allow"), "PA")
    if position != "DEF" and get("fum_lost"):
        add(get("fum_lost"), "FUM")
    return tokens


# --------------------------------------------------------------------------------------
# Fantasy tab
# --------------------------------------------------------------------------------------


async def scoring_leagues(session: AsyncSession) -> list[ScoringLeague]:
    rows = (
        await session.execute(
            select(League, Team)
            .outerjoin(Team, (Team.league_id == League.id) & Team.is_user_team.is_(True))
            .where(League.is_enabled.is_(True))
            .order_by(League.name, League.id)
        )
    ).all()
    seen: dict[str, ScoringLeague] = {}
    for league, team in rows:
        if league.id not in seen:
            seen[league.id] = ScoringLeague(
                league_id=league.id,
                name=league.name,
                platform=league.platform,
                scoring_type=league.scoring_type,
                team_id=team.id if team is not None else None,
            )
    return list(seen.values())


def _position(raw: str | None) -> FantasyPosition | None:
    value = "DEF" if raw in ("DST", "DEF") else raw
    return value if value in POSITIONS else None  # type: ignore[return-value]


def _short_name(first: str, last: str) -> str:
    return f"{first[0]}. {last}" if first and last else (last or first)


def _sort_key(player: FantasyPlayer, started: bool) -> tuple[float, float]:
    points = player.points if player.points is not None else -1.0
    projection = player.projection if player.projection is not None else -1.0
    return (points, projection) if started else (projection, points)


async def game_detail(
    session: AsyncSession, game_id: str, league_id: str | None, week: int | None = None
) -> GameDetail | None:
    found = await find_game(session, game_id, week)
    if found is None:
        return None
    season, week, event = found
    game = score_game(event)
    sides = {game.away.abbr: "away", game.home.abbr: "home"}
    team_names = {game.away.abbr: event["away"], game.home.abbr: event["home"]}

    leagues = await scoring_leagues(session)
    selected = next((lg for lg in leagues if lg.league_id == league_id), None) or (
        leagues[0] if leagues else None
    )
    fmt, fallback = resolve_format(selected.scoring_type if selected else None)
    points_key = _FORMAT_KEY[fmt]
    started = game.state in ("in", "post")
    final = game.state == "post"

    stat_rows = {
        row.sleeper_id: row
        for row in (
            await session.execute(
                select(PlayerWeeklyStat).where(
                    PlayerWeeklyStat.season == season,
                    PlayerWeeklyStat.week == week,
                    PlayerWeeklyStat.team.in_(sides),
                )
            )
        ).scalars()
    }
    projections = {
        sid: proj
        for sid, proj in (await nfl_week_cache.read_projections(session, season, week)).items()
        if proj.get("team") in sides
    }

    # Who's listed: everyone with a stat line, plus — until the game's over — everyone
    # projected to score. After the final whistle a projection with no line is a DNP.
    ids = set(stat_rows)
    if not final:
        ids |= {
            sid
            for sid, proj in projections.items()
            if (proj.get(points_key) or 0) >= MIN_LISTED_PROJECTION
        }

    our_players: dict[str, list[Player]] = {}
    if ids:
        for row in (
            await session.execute(select(Player).where(Player.sleeper_id.in_(ids)))
        ).scalars():
            our_players.setdefault(row.sleeper_id or "", []).append(row)

    league_slots: dict[str, tuple[RosterSlot, Team, Player]] = {}
    if selected is not None and ids:
        for slot, team, player in (
            await session.execute(
                select(RosterSlot, Team, Player)
                .join(Team, Team.id == RosterSlot.team_id)
                .join(Player, Player.id == RosterSlot.player_id)
                .where(
                    Team.league_id == selected.league_id,
                    RosterSlot.week == week,
                    Player.sleeper_id.in_(ids),
                )
            )
        ).all():
            league_slots[player.sleeper_id or ""] = (slot, team, player)

    grouped: dict[FantasyPosition, dict[str, list[FantasyPlayer]]] = {
        pos: {"away": [], "home": []} for pos in POSITIONS
    }
    stats_as_of: datetime | None = None
    for sid in ids:
        stat_row = stat_rows.get(sid)
        proj = projections.get(sid) or {}
        ours = our_players.get(sid) or []
        slot_entry = league_slots.get(sid)
        team = (stat_row.team if stat_row is not None else None) or proj.get("team")
        side = sides.get(team or "")
        position = _position(proj.get("position") or (ours[0].position if ours else None))
        if side is None or position is None:
            continue

        if position == "DEF":
            side_info = team_names[team]
            name = f"{side_info['location']} {side_info['name']}".strip()
            short_name = side_info["name"] or name
        elif proj.get("last_name"):
            name = f"{proj.get('first_name', '')} {proj['last_name']}".strip()
            short_name = _short_name(proj.get("first_name", ""), proj["last_name"])
        elif ours:
            name = ours[0].name
            first, _, last = name.partition(" ")
            short_name = _short_name(first, last)
        else:
            continue

        stats = json.loads(stat_row.stats_json or "{}") if stat_row is not None else {}
        if stat_row is not None:
            stats_as_of = max(stats_as_of or stat_row.fetched_at, stat_row.fetched_at)

        if slot_entry is not None:
            slot, fantasy_team, our_player = slot_entry
            points = slot.actual_points if started else None
            projection: float | None = slot.proj_points
            source = "league"
        else:
            fantasy_team, our_player = None, None
            points = (getattr(stat_row, points_key) or 0.0) if stat_row is not None else 0.0
            points = points if started else None
            projection = proj.get(points_key)
            source = "estimated"

        display_player = our_player or next(
            (p for p in ours if selected is not None and p.platform == selected.platform),
            ours[0] if ours else None,
        )
        grouped[position][side].append(
            FantasyPlayer(
                sleeper_id=sid,
                name=name,
                short_name=short_name,
                position=position,
                team=team or "",
                points=round(points, 2) if points is not None else None,
                projection=round(projection, 2) if projection is not None else None,
                source=source,  # type: ignore[arg-type]
                stats=stats,
                stat_line=_tokens(stats, position),
                player=_player_schema(display_player) if display_player is not None else None,
                fantasy_team=fantasy_team.name if fantasy_team is not None else None,
                is_mine=bool(fantasy_team is not None and fantasy_team.is_user_team),
            )
        )

    groups = []
    for position in POSITIONS:
        away = sorted(grouped[position]["away"], key=lambda p: _sort_key(p, started), reverse=True)
        home = sorted(grouped[position]["home"], key=lambda p: _sort_key(p, started), reverse=True)
        if away or home:
            groups.append(FantasyGroup(position=position, away=away, home=home))

    return GameDetail(
        season=season,
        week=week,
        game=game,
        leagues=leagues,
        league_id=selected.league_id if selected else None,
        points_format=fmt,
        points_format_fallback=fallback,
        groups=groups,
        stats_as_of=_utc(stats_as_of) if stats_as_of is not None else None,
    )
