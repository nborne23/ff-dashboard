"""Matchup context for the player card's game log: how generous each defense has been to
each position, and where a player's season ranks at his own (player game log).

Both need every stored stat line's POSITION, which `player_weekly_stats` doesn't carry —
it lives in Sleeper's 14 MB player dump. Parsing that on a card open (and on every live
refetch) is far too slow for the target iMac, so the work happens where the dump is
already in memory: the `refresh_player_stats` full pass, every 30 minutes. The result is
one compact JSON blob per season, kept in `http_cache` under this app's own namespace —
derived data rather than an upstream response, but it shares the store's shape exactly
(a keyed JSON document with a fetch time) and needs no migration.

Opponent rank ("@LAC (26th)"): fantasy points allowed to the position per game over the
season's COMPLETED weeks, ranked so that 1st is the most allowed — the easiest matchup —
the way Yahoo prints it. The in-progress week is left out: half a Sunday would rank a
defense on a game that is still going.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import PlayerWeeklyStat
from backend.gridiron.platforms import nfl_schedule
from backend.gridiron.services import cache

logger = logging.getLogger("uvicorn.error")

CACHE_PLATFORM = "gridiron"
CACHE_ENDPOINT = "matchup_ranks"

# Recomputed on every full pass and read stale or not, so the expiry is nominal —
# `http_cache` just requires one.
RANKS_TTL = timedelta(days=7)

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
# Our format name -> the `player_weekly_stats` column holding it.
FORMAT_COLUMNS = {"ppr": "pts_ppr", "half_ppr": "pts_half_ppr", "standard": "pts_std"}

# Sleeper calls a team defense "DEF"; everything here calls it "DST".
_SLEEPER_POSITIONS = {"DEF": "DST"}


@dataclass(frozen=True)
class StatLine:
    sleeper_id: str
    week: int
    opponent: str | None
    pts_ppr: float | None
    pts_half_ppr: float | None
    pts_std: float | None

    def points(self, fmt: str) -> float:
        return getattr(self, FORMAT_COLUMNS[fmt]) or 0.0


def positions_from_dump(dump: dict) -> dict[str, str]:
    """sleeper_id -> position in our vocabulary, for the six fantasy positions only."""
    out: dict[str, str] = {}
    for sleeper_id, entry in dump.items():
        if not isinstance(entry, dict):
            continue
        position = _SLEEPER_POSITIONS.get(entry.get("position"), entry.get("position"))
        if position in POSITIONS:
            out[str(sleeper_id)] = position
    return out


def _ordinal_ranks(totals: dict[str, float]) -> dict[str, int]:
    """Highest total ranks 1st. Ties break on the key so a recompute is stable."""
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {key: index + 1 for index, (key, _) in enumerate(ordered)}


def compute(
    lines: list[StatLine],
    positions: dict[str, str],
    numbers: dict[str, str],
    *,
    season: int,
    through_week: int,
) -> dict:
    """The blob `refresh` stores. Pure, so the ranking rules are testable without a DB."""
    # ---- points allowed per defense, per position, per game --------------------------
    completed = [line for line in lines if line.week <= through_week and line.opponent]
    games: dict[str, set[int]] = {}
    for line in completed:
        games.setdefault(line.opponent, set()).add(line.week)  # type: ignore[arg-type]

    dvp: dict[str, dict[str, dict[str, int]]] = {}
    for position in POSITIONS:
        dvp[position] = {}
        for fmt in FORMAT_COLUMNS:
            allowed = {team: 0.0 for team in games}
            for line in completed:
                if positions.get(line.sleeper_id) == position:
                    allowed[line.opponent] += line.points(fmt)  # type: ignore[index]
            per_game = {team: total / len(games[team]) for team, total in allowed.items()}
            dvp[position][fmt] = _ordinal_ranks(per_game)

    # ---- season points rank within each position -------------------------------------
    pos_rank: dict[str, dict[str, int]] = {}
    for fmt in FORMAT_COLUMNS:
        by_position: dict[str, dict[str, float]] = {}
        for line in lines:
            position = positions.get(line.sleeper_id)
            if position is None:
                continue
            bucket = by_position.setdefault(position, {})
            bucket[line.sleeper_id] = bucket.get(line.sleeper_id, 0.0) + line.points(fmt)
        pos_rank[fmt] = {
            sleeper_id: rank
            for bucket in by_position.values()
            for sleeper_id, rank in _ordinal_ranks(bucket).items()
        }

    seen = {line.sleeper_id for line in lines}
    return {
        "season": season,
        "through_week": through_week if completed else 0,
        "teams": len(games),
        "dvp": dvp,
        "pos_rank": pos_rank,
        "numbers": {sid: number for sid, number in numbers.items() if sid in seen},
    }


def _numbers_from_dump(dump: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for sleeper_id, entry in dump.items():
        if isinstance(entry, dict) and entry.get("number") not in (None, ""):
            out[str(sleeper_id)] = str(entry["number"])
    return out


async def refresh(session: AsyncSession, dump: dict, season: int, current_week: int) -> None:
    """Recompute `season`'s ranks from the stored stat lines and the in-memory dump."""
    rows = (
        await session.execute(
            select(
                PlayerWeeklyStat.sleeper_id,
                PlayerWeeklyStat.week,
                PlayerWeeklyStat.opponent,
                PlayerWeeklyStat.pts_ppr,
                PlayerWeeklyStat.pts_half_ppr,
                PlayerWeeklyStat.pts_std,
            ).where(PlayerWeeklyStat.season == season)
        )
    ).all()
    blob = compute(
        [StatLine(*row) for row in rows],
        positions_from_dump(dump),
        _numbers_from_dump(dump),
        season=season,
        through_week=current_week - 1,
    )
    expires_at = datetime.now(UTC).replace(tzinfo=None) + RANKS_TTL
    await cache.set(
        session, CACHE_PLATFORM, CACHE_ENDPOINT, {"season": season}, json.dumps(blob), expires_at
    )


async def refresh_context(
    session: AsyncSession,
    schedule_source: nfl_schedule.ScheduleSource,
    dump: dict,
    season: int,
    current_week: int,
) -> None:
    """Everything the game log needs beyond the stat lines: the season's schedule and
    these ranks. Called at the end of the stats full pass, and fail-soft on its own —
    a schedule outage must not cost the stat lines that pass already committed."""
    try:
        await nfl_schedule.refresh(session, schedule_source, season)
    except (httpx.HTTPError, ValueError) as exc:
        await session.rollback()
        logger.warning("nfl schedule %d unavailable: %s: %s", season, type(exc).__name__, exc)
    await refresh(session, dump, season, current_week)


@dataclass(frozen=True)
class MatchupRanks:
    season: int
    through_week: int
    teams: int
    dvp: dict[str, dict[str, dict[str, int]]]
    pos_rank: dict[str, dict[str, int]]
    numbers: dict[str, str]

    def opponent_rank(self, position: str, fmt: str, team: str | None) -> int | None:
        if not team:
            return None
        return self.dvp.get(position, {}).get(fmt, {}).get(team)

    def position_rank(self, fmt: str, sleeper_id: str | None) -> int | None:
        if not sleeper_id:
            return None
        return self.pos_rank.get(fmt, {}).get(sleeper_id)

    def jersey(self, sleeper_id: str | None) -> str | None:
        return self.numbers.get(sleeper_id) if sleeper_id else None


async def get_cached(session: AsyncSession, season: int) -> MatchupRanks | None:
    entry = await cache.get(session, CACHE_PLATFORM, CACHE_ENDPOINT, {"season": season})
    if entry is None or not entry.raw_json:
        return None
    try:
        blob = json.loads(entry.raw_json)
        return MatchupRanks(
            season=int(blob["season"]),
            through_week=int(blob.get("through_week") or 0),
            teams=int(blob.get("teams") or 0),
            dvp=blob.get("dvp") or {},
            pos_rank=blob.get("pos_rank") or {},
            numbers=blob.get("numbers") or {},
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
