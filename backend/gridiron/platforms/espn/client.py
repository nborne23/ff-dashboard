"""httpx wrapper around ESPN's unofficial Fantasy API using SWID/espn_s2 cookie auth."""

import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.config import Settings
from backend.gridiron.db import async_session_factory
from backend.gridiron.errors import AuthRequiredError
from backend.gridiron.services import cache

AUTH_FAILURE_STATUSES = (401, 403)

# Per platform-integrations spec's "Cache TTL by endpoint class" scenario (off-day defaults).
LEAGUE_SETTINGS_TTL = timedelta(hours=24)
TEAM_METADATA_TTL = timedelta(hours=6)
ROSTER_TTL = timedelta(hours=1)


class EspnClient:
    def __init__(
        self,
        settings: Settings,
        swid: str,
        espn_s2: str,
        http_client: httpx.AsyncClient | None = None,
        session_factory: async_sessionmaker | None = None,
    ) -> None:
        self._swid = swid
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.espn_base_url,
            timeout=15,
            headers={"Cookie": f"SWID={swid}; espn_s2={espn_s2}"},
        )
        self._owns_http = http_client is None
        # Cache-checked methods (get_league/get_roster/get_matchup) need a DB session;
        # defaults to the app-wide factory, overridable so tests can point at a tmp DB.
        self._session_factory = session_factory or async_session_factory

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def request(
        self, method: str, path: str, *, params: dict | None = None, **kwargs
    ) -> httpx.Response:
        response = await self._http.request(method, path, params=params, **kwargs)
        if response.status_code in AUTH_FAILURE_STATUSES:
            raise AuthRequiredError(f"espn auth required (status {response.status_code})")
        response.raise_for_status()
        return response

    async def get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        return await self.request("GET", path, params=params)

    async def probe_league(self, year: int) -> httpx.Response:
        """Cheap credential-verification call used by `POST /api/connections/espn/test`."""
        return await self.get(
            f"/apis/v3/games/ffl/seasons/{year}/segments/0/leagues",
            params={"view": "mTeam"},
        )

    @staticmethod
    def _league_path(league_id: int, year: int) -> str:
        return f"/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"

    async def _cached_league_fetch(
        self,
        league_id: int,
        year: int,
        endpoint: str,
        http_params: dict,
        ttl: timedelta,
    ) -> dict:
        """Cache-checked fetch shared by `get_league`/`get_roster`/`get_matchup`.

        On a fresh cache hit, returns the cached raw JSON without an outbound HTTP call.
        On a miss (or expired entry), fetches from ESPN, stores the raw response text
        in `http_cache` (design.md D7 — we keep raw responses to replay/debug platform
        schema changes), and returns the parsed body. `league_id`/`year` are folded into
        the cache key alongside `http_params` so distinct leagues/years/weeks never collide,
        even though they're also baked into the request path rather than sent as params.
        """
        cache_params = {**http_params, "league_id": league_id, "year": year}
        async with self._session_factory() as session:
            cached = await cache.get(session, "espn", endpoint, cache_params)
            if cached is not None and not cached.is_expired:
                return json.loads(cached.raw_json)

            response = await self.get(self._league_path(league_id, year), params=http_params)
            raw_text = response.text
            fetched_at = datetime.now(UTC)
            await cache.set(
                session,
                "espn",
                endpoint,
                cache_params,
                raw_text,
                expires_at=fetched_at + ttl,
                fetched_at=fetched_at,
            )
            return json.loads(raw_text)

    async def get_league(self, league_id: int, year: int) -> dict:
        """League metadata + team list (`view=mSettings&view=mTeam`), cache-checked.

        Both views come back in one call, so the combined response is cached once —
        under `TEAM_METADATA_TTL` (6h), the shorter of the two applicable TTLs from the
        platform-integrations spec's TTL table. Refreshing league settings more often
        than their 24h floor is safe; it just means slightly more frequent upstream
        calls than the strict minimum.
        """
        return await self._cached_league_fetch(
            league_id,
            year,
            "league",
            {"view": ["mSettings", "mTeam"]},
            TEAM_METADATA_TTL,
        )

    async def _get_roster_matchup(
        self,
        league_id: int,
        year: int,
        scoring_period: int,
        current_week: int | None = None,
    ) -> dict:
        """Shared fetch for `get_roster`/`get_matchup` — one call, stacked views.

        Per the platform-integrations spec's "Current-week roster + matchup" scenario,
        `scoringPeriodId` and `matchupPeriodId` are set to the same `scoring_period` —
        this already includes `mBoxscore`, unconditionally, for both current and past
        weeks (task 9.4: per-player scoring for a completed week needs nothing extra
        beyond requesting that week's own `scoring_period`).

        `current_week` (task 9.5), when passed, lets `cache_service.select_ttl` upgrade
        the TTL to `PAST_WEEK_TTL` for a `scoring_period` well behind the league's actual
        current week; omitted (the default), behavior is unchanged from before task 9.5.
        """
        return await self._cached_league_fetch(
            league_id,
            year,
            "roster_matchup",
            {
                "view": ["mRoster", "mMatchupScore", "mBoxscore"],
                "scoringPeriodId": scoring_period,
                "matchupPeriodId": scoring_period,
            },
            cache.select_ttl(scoring_period, current_week, ROSTER_TTL),
        )

    async def get_roster(
        self, league_id: int, year: int, scoring_period: int, current_week: int | None = None
    ) -> dict:
        """Raw roster+matchup response for `scoring_period` (shares the cache entry
        with `get_matchup` — see `_get_roster_matchup`)."""
        return await self._get_roster_matchup(league_id, year, scoring_period, current_week)

    async def get_matchup(
        self, league_id: int, year: int, scoring_period: int, current_week: int | None = None
    ) -> dict:
        """Raw roster+matchup response for `scoring_period` (shares the cache entry
        with `get_roster` — see `_get_roster_matchup`)."""
        return await self._get_roster_matchup(league_id, year, scoring_period, current_week)
