"""httpx client + mapper/upsert for ESPN's public NFL scoreboard (task 8.2).

Distinct from `platforms/espn/client.py`: that's the *authenticated* fantasy API
(`lm-api-reads.fantasy.espn.com`, SWID/espn_s2 cookies, per-league/team data). This hits
ESPN's public, unauthenticated site API for raw NFL game state — no credentials, no
league/team gating, just "what's happening around the league right now." Polled every
30s by the `refresh_nfl_state` scheduler job (scheduler.py).
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import schemas
from backend.gridiron.models import LiveNflGame as LiveNflGameRow
from backend.gridiron.schemas.live_nfl_games import GameState

logger = logging.getLogger("uvicorn.error")

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

_VALID_STATES: tuple[GameState, ...] = ("pre", "in", "post", "postponed")


class NflScoreboardClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=15)
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_scoreboard(self) -> dict:
        response = await self._http.get(SCOREBOARD_URL)
        response.raise_for_status()
        return response.json()


def _parse_kickoff(date_str: str) -> datetime:
    """ESPN dates look like `"2023-09-10T17:00Z"` — normalize to the codebase's naive-UTC
    convention (matches `created_at`/`run_at`/etc. everywhere else)."""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.astimezone(UTC).replace(tzinfo=None)


def _map_state(status_type: dict) -> GameState:
    name = str(status_type.get("name") or "").upper()
    if "POSTPON" in name:
        return "postponed"
    state = status_type.get("state")
    return state if state in _VALID_STATES else "pre"


def _competitor(competitors: list[dict], home_away: str) -> dict:
    for competitor in competitors:
        if competitor.get("homeAway") == home_away:
            return competitor
    return {}


def _score(competitor: dict) -> int:
    try:
        return int(float(competitor.get("score") or 0))
    except (TypeError, ValueError):
        return 0


def map_scoreboard(payload: dict) -> list[schemas.LiveNflGame]:
    """Map ESPN's public scoreboard response to `LiveNflGame[]`.

    Best-effort per event: a malformed/unexpected event is logged and skipped rather than
    failing the whole poll — one bad game shouldn't hide the state of the other 15.
    """
    games: list[schemas.LiveNflGame] = []
    for event in payload.get("events", []):
        try:
            competition = event["competitions"][0]
            competitors = competition["competitors"]
            status = competition.get("status") or event.get("status") or {}
            status_type = status.get("type", {})
            state = _map_state(status_type)
            home = _competitor(competitors, "home")
            away = _competitor(competitors, "away")

            games.append(
                schemas.LiveNflGame(
                    nfl_game_id=str(event["id"]),
                    home_team=(home.get("team") or {}).get("abbreviation", ""),
                    away_team=(away.get("team") or {}).get("abbreviation", ""),
                    home_score=_score(home),
                    away_score=_score(away),
                    state=state,
                    clock=status.get("displayClock") if state == "in" else None,
                    period=status.get("period") if state == "in" else None,
                    kickoff_at=_parse_kickoff(event["date"]),
                )
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("skipping malformed scoreboard event: %s", exc)
    return games


async def upsert_games(session: AsyncSession, games: list[schemas.LiveNflGame]) -> None:
    """Upsert every mapped game into `live_nfl_games`. Existing rows for games that have
    dropped off the scoreboard (rare — a bye week/canceled game) are left as-is rather
    than deleted; the next real update overwrites them, and a stale "final" row is
    harmless (never counted as "live" by the classifier)."""
    for game in games:
        await session.merge(
            LiveNflGameRow(
                nfl_game_id=game.nfl_game_id,
                home_team=game.home_team,
                away_team=game.away_team,
                home_score=game.home_score,
                away_score=game.away_score,
                state=game.state,
                clock=game.clock,
                period=game.period,
                kickoff_at=game.kickoff_at,
            )
        )
    await session.commit()


async def fetch_and_upsert(
    session: AsyncSession, client: NflScoreboardClient | None = None
) -> list[schemas.LiveNflGame]:
    """Fetch the scoreboard, map it, upsert `live_nfl_games`, and return the mapped games
    (fed straight into `services/live_state.classify` — no need to re-read the DB)."""
    owns_client = client is None
    client = client or NflScoreboardClient()
    try:
        payload = await client.get_scoreboard()
        games = map_scoreboard(payload)
        await upsert_games(session, games)
        return games
    finally:
        if owns_client:
            await client.aclose()
