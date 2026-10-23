"""Read side of add-player-stats: one player's game log, season totals, and this week.

Everything here reads stored rows — `player_weekly_stats` for history, `roster_slots` for
the league's own numbers, and the ESPN roster payload `refresh_fantasy` already left in
`http_cache` for the live stat line and the league-exact points breakdown. Nothing
fetches upstream (design.md D7).
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import League, Player, PlayerWeeklyStat, RosterSlot, Team
from backend.gridiron.platforms.espn.client import (
    ROSTER_MATCHUP_ENDPOINT,
    EspnClient,
    roster_matchup_params,
)
from backend.gridiron.platforms.espn.mapper import STAT_SOURCE_ACTUAL, STAT_SPLIT_WEEK
from backend.gridiron.schemas.player_stats import (
    BreakdownLine,
    GameLogRow,
    PlayerStatsData,
    PointsFormat,
    PositionGroup,
    SeasonSummary,
    StatColumn,
    ThisWeek,
)
from backend.gridiron.services import cache
from backend.gridiron.services.fantasy_service import _current_season, current_week

# --------------------------------------------------------------------------------------
# Columns
# --------------------------------------------------------------------------------------


def _col(key: str, label: str, agg: str = "sum") -> StatColumn:
    return StatColumn(key=key, label=label, agg=agg)


_RUSHING = [_col("rush_att", "Car"), _col("rush_yd", "Rush Yds"), _col("rush_td", "Rush TD")]
_RECEIVING = [
    _col("rec_tgt", "Tgt"),
    _col("rec", "Rec"),
    _col("rec_yd", "Rec Yds"),
    _col("rec_td", "Rec TD"),
]
_FUMBLES = [_col("fum_lost", "FL")]

COLUMNS: dict[str, list[StatColumn]] = {
    "QB": [
        _col("pass_cmp", "Cmp"),
        _col("pass_att", "Att"),
        _col("pass_yd", "Pass Yds"),
        _col("pass_td", "Pass TD"),
        _col("pass_int", "Int"),
        *_RUSHING,
        *_FUMBLES,
    ],
    "RB": [*_RUSHING, *_RECEIVING, *_FUMBLES],
    "WR": [*_RECEIVING, *_RUSHING, *_FUMBLES],
    "TE": [*_RECEIVING, *_RUSHING, *_FUMBLES],
    "K": [
        _col("fgm", "FGM"),
        _col("fga", "FGA"),
        _col("fgm_lng", "Long", "max"),
        _col("xpm", "XPM"),
        _col("xpa", "XPA"),
    ],
    "DST": [
        _col("sack", "Sack"),
        _col("int", "Int"),
        _col("fum_rec", "FR"),
        _col("td", "TD"),
        _col("safe", "Sfty"),
        _col("pts_allow", "PA"),
        _col("yds_allow", "YA"),
    ],
}


def position_group(position: str) -> PositionGroup:
    return position if position in COLUMNS else "WR"  # type: ignore[return-value]


# --------------------------------------------------------------------------------------
# Points format
# --------------------------------------------------------------------------------------

_FORMAT_COLUMN = {"ppr": "pts_ppr", "half_ppr": "pts_half_ppr", "standard": "pts_std"}


def resolve_format(scoring_type: str | None) -> tuple[PointsFormat, bool]:
    """The format history is shown in, and whether that's a fallback.

    Unlike the projection column (`fantasy_service._resolve_points`), which shows nothing
    for a custom league, a game log with no points column at all is useless — so custom
    falls back to PPR and the response says so, for the panel to label.
    """
    if scoring_type in _FORMAT_COLUMN:
        return scoring_type, False  # type: ignore[return-value]
    return "ppr", scoring_type is not None


# --------------------------------------------------------------------------------------
# Estimated breakdown (Sleeper stat line, standard rules)
# --------------------------------------------------------------------------------------

_REC_POINTS = {"ppr": 1.0, "half_ppr": 0.5, "standard": 0.0}

# (stat key, label, points per unit). The defaults ESPN and Yahoo ship with; a league that
# changed any of them shows the difference on the reconciling line.
_OFFENSE_RULES = [
    ("pass_yd", "Passing yards", 0.04),
    ("pass_td", "Passing TD", 4.0),
    ("pass_int", "Interceptions thrown", -2.0),
    ("pass_2pt", "Passing 2-pt conversion", 2.0),
    ("rush_yd", "Rushing yards", 0.1),
    ("rush_td", "Rushing TD", 6.0),
    ("rush_2pt", "Rushing 2-pt conversion", 2.0),
    ("rec_yd", "Receiving yards", 0.1),
    ("rec_td", "Receiving TD", 6.0),
    ("rec_2pt", "Receiving 2-pt conversion", 2.0),
    ("fum_lost", "Fumbles lost", -2.0),
]
_KICKER_RULES = [
    ("fgm_0_19", "FG made 0-19", 3.0),
    ("fgm_20_29", "FG made 20-29", 3.0),
    ("fgm_30_39", "FG made 30-39", 3.0),
    ("fgm_40_49", "FG made 40-49", 4.0),
    ("fgm_50p", "FG made 50+", 5.0),
    ("xpm", "Extra points made", 1.0),
]
_DST_RULES = [
    ("sack", "Sacks", 1.0),
    ("int", "Interceptions", 2.0),
    ("fum_rec", "Fumble recoveries", 2.0),
    ("td", "Defensive / return TD", 6.0),
    ("safe", "Safeties", 2.0),
    ("blk_kick", "Blocked kicks", 2.0),
]
# (max points allowed inclusive, label, points)
_POINTS_ALLOWED_TIERS = [
    (0, "0 points allowed", 10.0),
    (6, "1-6 points allowed", 7.0),
    (13, "7-13 points allowed", 4.0),
    (20, "14-20 points allowed", 1.0),
    (27, "21-27 points allowed", 0.0),
    (34, "28-34 points allowed", -1.0),
    (10_000, "35+ points allowed", -4.0),
]

RECONCILE_LABEL = "Bonuses & league-specific scoring"


def estimate_breakdown(
    stats: dict[str, float], group: str, fmt: PointsFormat, total: float | None
) -> list[BreakdownLine]:
    """Price a stat line with standard rules, then reconcile to `total`.

    The reconciling line is the point: a breakdown that silently doesn't add up to the
    number on the roster row is worse than none. When `total` is None the lines are
    returned as they are.
    """
    lines: list[BreakdownLine] = []

    def add(key: str, label: str, per: float) -> None:
        value = stats.get(key) or 0
        if value:
            lines.append(BreakdownLine(label=label, stat_value=value, points=round(value * per, 2)))

    if group == "K":
        for rule in _KICKER_RULES:
            add(*rule)
    elif group == "DST":
        for rule in _DST_RULES:
            add(*rule)
        if "pts_allow" in stats:
            allowed = stats["pts_allow"]
            for ceiling, label, points in _POINTS_ALLOWED_TIERS:
                if allowed <= ceiling:
                    lines.append(BreakdownLine(label=label, stat_value=None, points=points))
                    break
    else:
        rec_points = _REC_POINTS[fmt]
        for key, label, per in _OFFENSE_RULES:
            add(key, label, per)
            if key == "rush_2pt" and rec_points:
                # Receptions sit with the receiving lines, in the order a box score reads.
                add("rec", "Receptions", rec_points)

    if total is not None:
        gap = round(total - sum(line.points for line in lines), 2)
        if abs(gap) >= 0.05:
            lines.append(BreakdownLine(label=RECONCILE_LABEL, stat_value=None, points=gap))
    return lines


# --------------------------------------------------------------------------------------
# ESPN: live stat line + league-exact breakdown from the cached roster payload
# --------------------------------------------------------------------------------------

# ESPN stat id -> our stat key, for the stat line. 53 rather than 41 for receptions: both
# carry the same count, and 53 is the one leagues score.
_ESPN_STAT_KEYS = {
    0: "pass_att",
    1: "pass_cmp",
    3: "pass_yd",
    4: "pass_td",
    20: "pass_int",
    23: "rush_att",
    24: "rush_yd",
    25: "rush_td",
    58: "rec_tgt",
    53: "rec",
    42: "rec_yd",
    43: "rec_td",
    72: "fum_lost",
    83: "fgm",
    84: "fga",
    86: "xpm",
    87: "xpa",
    99: "sack",
    95: "int",
    96: "fum_rec",
    98: "safe",
    120: "pts_allow",
    127: "yds_allow",
}

# ESPN stat id -> breakdown label. Only ids whose meaning is certain; anything else still
# appears, as "Other scoring", so the lines always sum to ESPN's own total.
ESPN_STAT_LABELS = {
    3: "Passing yards",
    4: "Passing TD",
    15: "40+ yd passing TD bonus",
    16: "50+ yd passing TD bonus",
    17: "300-399 passing yds bonus",
    18: "400+ passing yds bonus",
    19: "Passing 2-pt conversion",
    20: "Interceptions thrown",
    24: "Rushing yards",
    25: "Rushing TD",
    26: "Rushing 2-pt conversion",
    35: "40+ yd rushing TD bonus",
    36: "50+ yd rushing TD bonus",
    37: "100-199 rushing yds bonus",
    38: "200+ rushing yds bonus",
    42: "Receiving yards",
    43: "Receiving TD",
    44: "Receiving 2-pt conversion",
    45: "40+ yd receiving TD bonus",
    46: "50+ yd receiving TD bonus",
    53: "Receptions",
    56: "100-199 receiving yds bonus",
    57: "200+ receiving yds bonus",
    63: "Fumble recovered for TD",
    64: "Times sacked",
    68: "Fumbles",
    72: "Fumbles lost",
    74: "FG made 50+",
    76: "FG missed 50+",
    77: "FG made 40-49",
    79: "FG missed 40-49",
    80: "FG made 0-39",
    82: "FG missed 0-39",
    83: "FG made",
    85: "FG missed",
    86: "Extra points made",
    88: "Extra points missed",
    89: "0 points allowed",
    90: "1-6 points allowed",
    91: "7-13 points allowed",
    92: "14-17 points allowed",
    95: "Interceptions",
    96: "Fumble recoveries",
    97: "Blocked kicks",
    98: "Safeties",
    99: "Sacks",
    101: "Kick return TD",
    102: "Punt return TD",
    103: "Interception return TD",
    104: "Fumble return TD",
    106: "Forced fumbles",
    121: "18-21 points allowed",
    122: "22-27 points allowed",
    123: "28-34 points allowed",
    124: "35-45 points allowed",
    125: "46+ points allowed",
    128: "<100 yards allowed",
    129: "100-199 yards allowed",
    130: "200-299 yards allowed",
    131: "300-349 yards allowed",
    132: "350-399 yards allowed",
    133: "400-449 yards allowed",
    134: "450-499 yards allowed",
    135: "500-549 yards allowed",
    136: "550+ yards allowed",
}

# Tier awards: the raw "value" is a 0/1 flag, not a count worth printing.
_ESPN_TIER_IDS = frozenset({89, 90, 91, 92, *range(121, 126), *range(128, 137)})


def _espn_player_id(player: Player) -> int | None:
    try:
        return int(player.platform_id.removeprefix("p-"))
    except ValueError:
        return None


async def _espn_week_stat(
    session: AsyncSession, league: League, player: Player, week: int
) -> dict | None:
    """This player's actual-stats entry for `week` from the cached roster payload."""
    espn_id = _espn_player_id(player)
    if espn_id is None:
        return None
    params = EspnClient._cache_params(
        int(league.platform_id), league.season, roster_matchup_params(week)
    )
    entry = await cache.get(session, "espn", ROSTER_MATCHUP_ENDPOINT, params)
    if entry is None or not entry.raw_json:
        return None
    raw = json.loads(entry.raw_json)
    for team in raw.get("teams", []):
        for roster_entry in (team.get("roster") or {}).get("entries", []):
            raw_player = (roster_entry.get("playerPoolEntry") or {}).get("player") or {}
            if raw_player.get("id") != espn_id:
                continue
            for stat in raw_player.get("stats", []):
                if (
                    stat.get("scoringPeriodId") == week
                    and stat.get("statSourceId") == STAT_SOURCE_ACTUAL
                    and stat.get("statSplitTypeId", STAT_SPLIT_WEEK) == STAT_SPLIT_WEEK
                ):
                    return stat
            return None
    return None


def espn_stat_line(stat: dict) -> dict[str, float]:
    raw = stat.get("stats") or {}
    return {
        key: float(raw[str(espn_id)])
        for espn_id, key in _ESPN_STAT_KEYS.items()
        if str(espn_id) in raw
    }


def espn_breakdown(stat: dict) -> list[BreakdownLine]:
    raw = stat.get("stats") or {}
    lines = []
    for espn_id, points in (stat.get("appliedStats") or {}).items():
        if not points:
            continue
        sid = int(espn_id)
        lines.append(
            BreakdownLine(
                label=ESPN_STAT_LABELS.get(sid, f"Other scoring (ESPN stat {sid})"),
                stat_value=None if sid in _ESPN_TIER_IDS else raw.get(espn_id),
                points=round(points, 2),
            )
        )
    # Biggest contributors first — that is the question a breakdown answers.
    lines.sort(key=lambda line: abs(line.points), reverse=True)
    return lines


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def _totals(rows: list[GameLogRow], columns: list[StatColumn]) -> dict[str, float]:
    out: dict[str, float] = {}
    for column in columns:
        values = [row.stats[column.key] for row in rows if column.key in row.stats]
        if values:
            out[column.key] = max(values) if column.agg == "max" else round(sum(values), 2)
    return out


def summarize_seasons(game_log: list[GameLogRow], columns: list[StatColumn]) -> list[SeasonSummary]:
    by_season: dict[int, list[GameLogRow]] = {}
    for row in game_log:
        by_season.setdefault(row.season, []).append(row)
    summaries = []
    for season in sorted(by_season, reverse=True):
        rows = by_season[season]
        points = [r.fantasy_points for r in rows if r.fantasy_points is not None]
        total = round(sum(points), 2) if points else None
        summaries.append(
            SeasonSummary(
                season=season,
                team=max(rows, key=lambda r: r.week).team,
                games=len(rows),
                fantasy_points=total,
                ppg=round(total / len(points), 2) if points else None,
                stats=_totals(rows, columns),
            )
        )
    return summaries


async def _league_for_team(session: AsyncSession, team_id: str | None) -> League | None:
    if not team_id:
        return None
    team = await session.get(Team, team_id)
    return await session.get(League, team.league_id) if team is not None else None


async def _roster_slot(
    session: AsyncSession, player_id: str, week: int, team_id: str | None, league: League | None
) -> RosterSlot | None:
    """The player's slot this week in the viewing league — on the viewing team, or on
    another team in the same league (an opponent's player in Matchups)."""
    if league is None:
        return None
    rows = (
        (
            await session.execute(
                select(RosterSlot)
                .join(Team, Team.id == RosterSlot.team_id)
                .where(
                    RosterSlot.player_id == player_id,
                    RosterSlot.week == week,
                    Team.league_id == league.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return next((r for r in rows if r.team_id == team_id), rows[0] if rows else None)


async def build(
    session: AsyncSession, player: Player, team_id: str | None, week: int | None
) -> PlayerStatsData:
    league = await _league_for_team(session, team_id)
    fmt, fallback = resolve_format(league.scoring_type if league else None)
    points_column = _FORMAT_COLUMN[fmt]
    group = position_group(player.position)
    columns = COLUMNS[group]

    season = league.season if league else _current_season()
    live_week = await current_week(session)
    week = week or live_week

    stored: list[PlayerWeeklyStat] = []
    if player.sleeper_id:
        stored = list(
            (
                await session.execute(
                    select(PlayerWeeklyStat)
                    .where(PlayerWeeklyStat.sleeper_id == player.sleeper_id)
                    .order_by(PlayerWeeklyStat.season.desc(), PlayerWeeklyStat.week)
                )
            )
            .scalars()
            .all()
        )
    game_log = [
        GameLogRow(
            season=row.season,
            week=row.week,
            date=row.game_date,
            team=row.team,
            opponent=row.opponent,
            fantasy_points=getattr(row, points_column),
            stats=json.loads(row.stats_json or "{}"),
        )
        for row in stored
    ]

    # ---- this week ------------------------------------------------------------------
    slot = await _roster_slot(session, player.id, week, team_id, league)
    sleeper_row = next((r for r in game_log if r.season == season and r.week == week), None)
    final = week < live_week
    league_points = slot.actual_points if slot is not None else None
    # Reconcile only once the week is final. Mid-week the league score and Sleeper's line
    # refresh on different clocks, so the gap between them is lag, not scoring rules, and
    # a "bonuses -6.9" line built from it would be a confident wrong answer.
    reconcile_to = league_points if final and league_points is not None else None

    stats: dict[str, float] | None = None
    stats_source = None
    breakdown: list[BreakdownLine] = []
    breakdown_source = None

    espn_stat = None
    if player.platform == "espn" and league is not None and league.platform == "espn":
        espn_stat = await _espn_week_stat(session, league, player, week)
    if espn_stat is not None:
        stats, stats_source = espn_stat_line(espn_stat), "espn"
        breakdown, breakdown_source = espn_breakdown(espn_stat), "league"
    elif sleeper_row is not None:
        stats, stats_source = sleeper_row.stats, "sleeper"
        breakdown = estimate_breakdown(sleeper_row.stats, group, fmt, reconcile_to)
        breakdown_source = "estimated"

    this_week = ThisWeek(
        season=season,
        week=week,
        final=final,
        opponent=(
            sleeper_row.opponent
            if sleeper_row is not None and sleeper_row.opponent
            else (player.nfl_opponent if week == live_week else None)
        ),
        is_live=bool(slot.is_live) if slot is not None else False,
        status_text=slot.status_text if slot is not None else None,
        league_points=league_points,
        league_proj=slot.proj_points if slot is not None else None,
        stats=stats,
        stats_source=stats_source,
        breakdown=breakdown,
        breakdown_source=breakdown_source,
        breakdown_total=round(sum(line.points for line in breakdown), 2) if breakdown else None,
    )

    return PlayerStatsData(
        player_id=player.id,
        sleeper_id=player.sleeper_id,
        position_group=group,
        points_format=fmt,
        points_format_fallback=fallback,
        columns=columns,
        this_week=this_week,
        seasons=summarize_seasons(game_log, columns),
        game_log=game_log,
    )
