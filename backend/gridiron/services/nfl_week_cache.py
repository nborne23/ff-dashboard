"""Per-week NFL scoreboards and all-player projections, kept in `http_cache` (add-nfl-scores).

Two writers, one reader:

- `nfl_scoreboard.fetch_and_upsert` stores the CURRENT week's scoreboard on every
  `refresh_nfl_state` tick, before that tick publishes the `live_nfl_games` scope — so a
  refetch triggered by the signal always finds the payload the signal was about.
- `platforms/nfl_weeks.py` (the `refresh_nfl_weeks` job) sweeps every regular-season week
  and Sleeper's per-week projections, which is what lets the Scores screen switch weeks
  without fetching on read (design.md D7).
- `services/scores.py` reads both.

Payloads are TRIMMED before they're stored: ESPN's scoreboard is ~130 KB a week, almost
all of it links, venues and headlines nothing renders; the projection feed carries a
whole player record and ~20 stat keys per row. What's kept is what the screens draw.

Team abbreviations are normalized to the app's (and Sleeper's) vocabulary on the way in.
ESPN is the odd one out with `WSH` for Washington; everything else in the codebase —
Sleeper, both fantasy platforms' mappers, `players.nfl_team` — says `WAS`.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.services import cache

logger = logging.getLogger("uvicorn.error")

ESPN_PLATFORM = "espn_public"
WEEK_ENDPOINT = "nfl_week"
CURRENT_ENDPOINT = "nfl_week_current"
PROJECTIONS_PLATFORM = "sleeper"
PROJECTIONS_ENDPOINT = "week_projections"

# Regular season only. ESPN's `seasontype=2`; the postseason (3) is out of scope.
REGULAR_SEASON = 2
MAX_WEEK = 18

# Read paths ignore expiry (D7) — this only feeds `CacheEntry.is_expired` for anyone who
# wants to know how stale a week is. The job decides what to refetch on its own terms.
TTL = timedelta(hours=6)

_ESPN_TO_APP_TEAM = {"WSH": "WAS"}

_STATES = ("pre", "in", "post", "postponed")


def normalize_team(abbr: str | None) -> str:
    """ESPN team abbreviation -> the app's. The one place this mapping lives."""
    value = (abbr or "").upper()
    return _ESPN_TO_APP_TEAM.get(value, value)


def _week_params(season: int, week: int) -> dict:
    return {"season": season, "week": week}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------------------
# ESPN scoreboard
# --------------------------------------------------------------------------------------


def _state(status_type: dict) -> str:
    if "POSTPON" in str(status_type.get("name") or "").upper():
        return "postponed"
    state = status_type.get("state")
    return state if state in _STATES else "pre"


def _int(value: object) -> int | None:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _side(competitor: dict) -> dict:
    team = competitor.get("team") or {}
    records = competitor.get("records") or []
    return {
        "espn_team_id": str(team.get("id") or ""),
        "abbr": normalize_team(team.get("abbreviation")),
        "name": team.get("name") or team.get("shortDisplayName") or "",
        "location": team.get("location") or "",
        "record": records[0].get("summary") if records else None,
        "score": _int(competitor.get("score")),
        "logo": team.get("logo"),
        "color": team.get("color"),
        "linescores": [
            v
            for v in (_int(ls.get("value")) for ls in competitor.get("linescores") or [])
            if v is not None
        ],
        "winner": bool(competitor.get("winner")),
    }


_LEADER_CATEGORIES = {
    "passingYards": "passing",
    "rushingYards": "rushing",
    "receivingYards": "receiving",
}


def _leaders(competition: dict, team_abbr_by_id: dict[str, str]) -> list[dict]:
    out = []
    for category in competition.get("leaders") or []:
        kind = _LEADER_CATEGORIES.get(category.get("name"))
        leaders = category.get("leaders") or []
        if kind is None or not leaders:
            continue
        leader = leaders[0]
        athlete = leader.get("athlete") or {}
        team_id = str((leader.get("team") or athlete.get("team") or {}).get("id") or "")
        out.append(
            {
                "category": kind,
                "athlete_id": str(athlete.get("id") or ""),
                "name": athlete.get("displayName") or athlete.get("fullName") or "",
                "short_name": athlete.get("shortName") or athlete.get("displayName") or "",
                "position": (athlete.get("position") or {}).get("abbreviation"),
                "team": team_abbr_by_id.get(team_id, ""),
                "display_value": leader.get("displayValue") or "",
            }
        )
    return out


def _situation(competition: dict, team_abbr_by_id: dict[str, str]) -> dict | None:
    situation = competition.get("situation")
    if not situation:
        return None
    return {
        "possession": team_abbr_by_id.get(str(situation.get("possession") or "")),
        "down_distance": situation.get("shortDownDistanceText")
        or situation.get("downDistanceText"),
        "is_red_zone": bool(situation.get("isRedZone")),
    }


def _event(event: dict) -> dict:
    competition = event["competitions"][0]
    competitors = competition["competitors"]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    home = next(c for c in competitors if c.get("homeAway") == "home")
    away = next(c for c in competitors if c.get("homeAway") == "away")
    home_side, away_side = _side(home), _side(away)
    by_id = {
        home_side["espn_team_id"]: home_side["abbr"],
        away_side["espn_team_id"]: away_side["abbr"],
    }
    broadcasts = [n for b in competition.get("broadcasts") or [] for n in b.get("names") or []]
    return {
        "id": str(event["id"]),
        "kickoff_at": event["date"],
        "state": _state(status_type),
        "status_name": status_type.get("name") or "",
        "short_detail": status_type.get("shortDetail") or "",
        "period": _int(status.get("period")),
        "clock": status.get("displayClock"),
        "broadcast": broadcasts[0] if broadcasts else None,
        "home": home_side,
        "away": away_side,
        "leaders": _leaders(competition, by_id),
        "situation": _situation(competition, by_id),
    }


def trim_scoreboard(payload: dict) -> dict | None:
    """ESPN's scoreboard response -> what the Scores screens read, or None when it isn't a
    regular-season week (the postseason and preseason are out of scope).

    Best-effort per event, like `nfl_scoreboard.map_scoreboard`: one malformed game is
    logged and dropped rather than hiding the other fifteen.
    """
    season = _int((payload.get("season") or {}).get("year"))
    season_type = _int((payload.get("season") or {}).get("type"))
    week = _int((payload.get("week") or {}).get("number"))
    if season is None or week is None or season_type != REGULAR_SEASON:
        return None
    events = []
    for event in payload.get("events") or []:
        try:
            events.append(_event(event))
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            logger.warning("skipping malformed scoreboard event: %s", exc)
    return {
        "season": season,
        "week": week,
        "byes": sorted(
            normalize_team(t.get("abbreviation"))
            for t in (payload.get("week") or {}).get("teamsOnBye") or []
        ),
        "events": events,
    }


async def store_week(session: AsyncSession, trimmed: dict, *, current: bool = False) -> None:
    """Write one trimmed week; `current=True` also moves the "current week" pointer."""
    now = _now()
    season, week = trimmed["season"], trimmed["week"]
    await cache.set(
        session,
        ESPN_PLATFORM,
        WEEK_ENDPOINT,
        _week_params(season, week),
        json.dumps(trimmed, separators=(",", ":")),
        now + TTL,
        fetched_at=now,
    )
    if current:
        await cache.set(
            session,
            ESPN_PLATFORM,
            CURRENT_ENDPOINT,
            None,
            json.dumps({"season": season, "week": week}),
            now + TTL,
            fetched_at=now,
        )


async def store_scoreboard(session: AsyncSession, payload: dict, *, current: bool) -> None:
    """Trim and store a raw ESPN scoreboard. Never raises: the live-state tick that calls
    this must not fail because the Scores screen's copy couldn't be written."""
    try:
        trimmed = trim_scoreboard(payload)
        if trimmed is not None:
            await store_week(session, trimmed, current=current)
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception("could not cache the NFL scoreboard week")


async def read_current(session: AsyncSession) -> tuple[int, int] | None:
    """(season, week) as ESPN's scoreboard last called it current, or None if never seen."""
    entry = await cache.get(session, ESPN_PLATFORM, CURRENT_ENDPOINT, None)
    if entry is None:
        return None
    value = json.loads(entry.raw_json)
    return int(value["season"]), int(value["week"])


async def read_week(session: AsyncSession, season: int, week: int) -> tuple[dict, datetime] | None:
    """The trimmed scoreboard for a week and when it was fetched, or None if never cached."""
    entry = await cache.get(session, ESPN_PLATFORM, WEEK_ENDPOINT, _week_params(season, week))
    if entry is None:
        return None
    return json.loads(entry.raw_json), entry.fetched_at


# --------------------------------------------------------------------------------------
# Sleeper projections, every player
# --------------------------------------------------------------------------------------

_POINT_KEYS = ("pts_ppr", "pts_half_ppr", "pts_std")


def trim_projections(rows: list[dict]) -> dict[str, dict]:
    """Sleeper projection rows -> `{sleeper_id: {...}}` for players on an NFL team.

    Unlike `player_projections`, which only keeps players already in `players`, this is
    every player Sleeper projects — a pre-game Fantasy tab lists both depth charts, most
    of whom nobody in the user's leagues rosters. It doubles as the name source for
    players who only appear in `player_weekly_stats` (which stores ids, not names).

    Free agents (no team) are dropped: they can't appear in a game.
    """
    out: dict[str, dict] = {}
    for row in rows:
        player = row.get("player") or {}
        team = row.get("team") or player.get("team")
        sleeper_id = row.get("player_id")
        if not sleeper_id or not team:
            continue
        stats = row.get("stats") or {}
        out[str(sleeper_id)] = {
            "first_name": player.get("first_name") or "",
            "last_name": player.get("last_name") or "",
            "position": player.get("position") or "",
            "team": normalize_team(team),
            **{key: stats[key] for key in _POINT_KEYS if stats.get(key)},
        }
    return out


async def store_projections(
    session: AsyncSession, season: int, week: int, players: dict[str, dict]
) -> None:
    now = _now()
    await cache.set(
        session,
        PROJECTIONS_PLATFORM,
        PROJECTIONS_ENDPOINT,
        _week_params(season, week),
        json.dumps(players, separators=(",", ":")),
        now + TTL,
        fetched_at=now,
    )


async def read_projections(session: AsyncSession, season: int, week: int) -> dict[str, dict]:
    entry = await cache.get(
        session, PROJECTIONS_PLATFORM, PROJECTIONS_ENDPOINT, _week_params(season, week)
    )
    return json.loads(entry.raw_json) if entry is not None else {}


async def has_projections(session: AsyncSession, season: int, week: int) -> bool:
    entry = await cache.get(
        session, PROJECTIONS_PLATFORM, PROJECTIONS_ENDPOINT, _week_params(season, week)
    )
    return entry is not None
