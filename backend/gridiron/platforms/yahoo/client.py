"""httpx wrapper around the Yahoo Fantasy Sports REST API.

Handles bearer-token injection, one-shot refresh-and-retry on 401, and exponential
backoff on 429/999 (Yahoo's own "too many requests" status).

Also provides cache-checked fetch methods for discovery (game key, leagues, team) and for
roster/matchup data. Discovery methods return small derived values (they're URL-navigation
helpers, not normalized entities) while `get_roster`/`get_matchup` return the raw parsed JSON
verbatim — mapping raw payloads into normalized `schemas` entities is `mapper.py`'s job, kept
separate so mappers stay pure and independently testable from fixtures.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings
from backend.gridiron.errors import AuthRequiredError, RateLimitedError
from backend.gridiron.platforms.yahoo import oauth
from backend.gridiron.platforms.yahoo._yahoo_json import (
    collection_items,
    find_subresource,
    flatten,
    nested_subresource,
    truthy,
)
from backend.gridiron.services import cache as cache_service

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

RATE_LIMIT_STATUSES = (429, 999)
BACKOFF_SECONDS = (1, 2, 4)  # exponential backoff; 3 retries max

# TTLs per platform-integrations spec's "Cache TTL by endpoint class" table. Roster and
# matchup use the off-day default here; the adaptive (game-day / live) TTLs land with the
# live_state work in a later task.
GAME_KEY_TTL = timedelta(hours=24)
LEAGUE_TTL = timedelta(hours=24)  # league settings / scoring rules
TEAM_TTL = timedelta(hours=6)  # team metadata
ROSTER_TTL = timedelta(hours=1)  # roster, off-day default
MATCHUP_TTL = timedelta(hours=1)  # matchup, off-day default
PLAYER_POOL_TTL = timedelta(hours=6)  # matches the ESPN pool's TTL

# Yahoo caps a players collection at 25 per request; the pool limit is the bandwidth
# budget for one league (300 = 12 requests), sorted best-available-first so the cut
# falls at the tail nobody claims from.
PLAYER_POOL_PAGE = 25
PLAYER_POOL_LIMIT = 300

# Called with (access_token, refresh_token) after a successful refresh so the caller
# can persist the new tokens.
TokenRefreshCallback = Callable[[str, str], Awaitable[None]]


class YahooClient:
    def __init__(
        self,
        settings: Settings,
        access_token: str,
        refresh_token: str,
        on_token_refresh: TokenRefreshCallback | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._on_token_refresh = on_token_refresh
        self._http = http_client or httpx.AsyncClient(base_url=BASE_URL, timeout=15)
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _refresh(self) -> None:
        try:
            tokens = await oauth.refresh_access_token(self._settings, self._refresh_token)
        except httpx.HTTPStatusError as exc:
            raise AuthRequiredError("yahoo token refresh failed") from exc

        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        if self._on_token_refresh is not None:
            await self._on_token_refresh(self._access_token, self._refresh_token)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        _retried_after_refresh: bool = False,
        **kwargs,
    ) -> httpx.Response:
        for attempt in range(len(BACKOFF_SECONDS) + 1):
            headers = {"Authorization": f"Bearer {self._access_token}"}
            response = await self._http.request(
                method, path, params=params, headers=headers, **kwargs
            )

            if response.status_code == 401 and not _retried_after_refresh:
                await self._refresh()
                return await self.request(
                    method, path, params=params, _retried_after_refresh=True, **kwargs
                )

            if response.status_code in RATE_LIMIT_STATUSES:
                if attempt < len(BACKOFF_SECONDS):
                    await asyncio.sleep(BACKOFF_SECONDS[attempt])
                    continue
                raise RateLimitedError(f"yahoo rate limited (status {response.status_code})")

            response.raise_for_status()
            return response

        raise RateLimitedError("yahoo rate limited")

    async def get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        return await self.request("GET", path, params=params)

    async def _cached_get(
        self,
        session: AsyncSession,
        *,
        endpoint: str,
        cache_params: dict | None,
        path: str,
        ttl: timedelta,
    ) -> dict:
        """Cache-checked GET: return cached raw JSON on a fresh hit, else fetch upstream,
        cache the response, and return it. `cache_params` (not the HTTP query string, which
        is always just `format=json` here — Yahoo's variable parts are matrix params baked
        into `path`) forms the cache row's `params_hash`."""
        entry = await cache_service.get(session, "yahoo", endpoint, cache_params)
        if entry is not None and not entry.is_expired:
            return json.loads(entry.raw_json)

        response = await self.get(path, params={"format": "json"})
        raw = response.json()
        fetched_at = datetime.now(UTC)
        await cache_service.set(
            session,
            "yahoo",
            endpoint,
            cache_params,
            json.dumps(raw),
            expires_at=fetched_at + ttl,
            fetched_at=fetched_at,
        )
        return raw

    async def resolve_game_key(self, session: AsyncSession) -> str:
        """Resolve the active NFL `game_key` (changes each season): fetch (or reuse the
        cached) games list, pick the entry with the highest `season` preferring
        `is_registration_over=0`, and return just the `game_key` string."""
        raw = await self._cached_get(
            session,
            endpoint="games",
            cache_params=None,
            path="/users;use_login=1/games;game_codes=nfl",
            ttl=GAME_KEY_TTL,
        )
        users_root = raw["fantasy_content"]["users"]
        user = find_subresource(collection_items(users_root)[0]["user"], "games")
        games = [flatten(item["game"]) for item in collection_items(user)]
        if not games:
            raise ValueError("yahoo returned no NFL games for this user")

        max_season = max(int(g["season"]) for g in games)
        candidates = [g for g in games if int(g["season"]) == max_season]
        for game in candidates:
            if not truthy(game.get("is_registration_over", 0)):
                return str(game["game_key"])
        return str(candidates[0]["game_key"])

    async def list_leagues_raw(self, session: AsyncSession, game_key: str) -> list[dict]:
        """Return the raw `{"league": [...]}` collection fragments for every league the user
        owns within `game_key` — the exact input shape `mapper.map_league` expects. Shares
        the cache entry with `list_leagues` (one upstream call feeds both)."""
        raw = await self._cached_get(
            session,
            endpoint="leagues",
            cache_params={"game_key": game_key},
            path=f"/users;use_login=1/games;game_keys={game_key}/leagues",
            ttl=LEAGUE_TTL,
        )
        users_root = raw["fantasy_content"]["users"]
        user = find_subresource(collection_items(users_root)[0]["user"], "games")

        items: list[dict] = []
        for game_item in collection_items(user):
            try:
                leagues_root = find_subresource(game_item["game"], "leagues")
            except KeyError:
                continue
            items.extend(collection_items(leagues_root))
        return items

    async def list_leagues(
        self, session: AsyncSession, game_key: str
    ) -> list[tuple[str, str, int, str]]:
        """Return `(league_key, name, num_teams, scoring_type)` for every league the user
        owns within `game_key`."""
        result: list[tuple[str, str, int, str]] = []
        for league_item in await self.list_leagues_raw(session, game_key):
            fields = flatten(league_item["league"])
            result.append(
                (
                    fields["league_key"],
                    fields["name"],
                    int(fields["num_teams"]),
                    fields["scoring_type"],
                )
            )
        return result

    async def list_teams_raw(self, session: AsyncSession, league_key: str) -> list[dict]:
        """Return the raw `{"team": [...]}` collection fragments for every team in
        `league_key` — the exact input shape `mapper.map_team` expects. Shares the cache
        entry with `get_team` (one upstream call feeds both).

        Fetched from `/standings` rather than `/teams`: the two return the same team
        fragments, but standings additionally carries `team_standings` (rank, W-L-T,
        points for/against) on each one. `/teams` alone leaves every Yahoo team at 0-0 and
        rank 0 — the ESPN league payload has those numbers inline, so this is what it takes
        to reach parity, and it costs no extra request.
        """
        raw = await self._cached_get(
            session,
            endpoint="standings",
            cache_params={"league_key": league_key},
            path=f"/league/{league_key}/standings",
            ttl=TEAM_TTL,
        )
        league_array = raw["fantasy_content"]["league"]
        standings_root = find_subresource(league_array, "standings")
        # Yahoo wraps the standings collection in a single-element array on some responses
        # and returns the object directly on others.
        if isinstance(standings_root, list):
            standings_root = standings_root[0]
        teams_root = nested_subresource(standings_root, "teams")
        return collection_items(teams_root)

    async def get_team(self, session: AsyncSession, league_key: str) -> str:
        """Find the team `is_owned_by_current_login=1` within `league_key` and return its
        `team_key`."""
        for team_item in await self.list_teams_raw(session, league_key):
            fields = flatten(team_item["team"])
            if truthy(fields.get("is_owned_by_current_login", 0)):
                return str(fields["team_key"])
        raise ValueError(f"no team owned by current login found in league {league_key}")

    async def get_roster(
        self,
        session: AsyncSession,
        team_key: str,
        week: int,
        current_week: int | None = None,
    ) -> dict:
        """Return the raw JSON for `team_key`'s week-`week` roster + stats. Mapping into
        `RosterSlot`s is `mapper.map_roster`'s job.

        `current_week` (task 9.5), when passed, lets `cache_service.select_ttl` upgrade
        the TTL to `PAST_WEEK_TTL` for a `week` well behind the league's actual current
        week; omitted (the default), behavior is unchanged from before task 9.5.
        """
        return await self._cached_get(
            session,
            endpoint="roster",
            cache_params={"team_key": team_key, "week": week},
            path=f"/team/{team_key}/roster;week={week}/players/stats",
            ttl=cache_service.select_ttl(week, current_week, ROSTER_TTL),
        )

    async def get_matchup(
        self,
        session: AsyncSession,
        team_key: str,
        week: int,
        current_week: int | None = None,
    ) -> dict:
        """Return the raw JSON for `team_key`'s week-`week` matchup. Mapping into a
        `Matchup` is `mapper.map_matchup`'s job. See `get_roster` for `current_week`."""
        return await self._cached_get(
            session,
            endpoint="matchup",
            cache_params={"team_key": team_key, "week": week},
            path=f"/team/{team_key}/matchups;weeks={week}",
            ttl=cache_service.select_ttl(week, current_week, MATCHUP_TTL),
        )

    async def list_player_pool_raw(
        self, session: AsyncSession, league_key: str, *, limit: int = PLAYER_POOL_LIMIT
    ) -> list[dict]:
        """Return the raw `{"player": [...]}` fragments for the claimable players in
        `league_key`, best-available first.

        Yahoo caps a players collection at `PLAYER_POOL_PAGE` per request and has no
        equivalent of ESPN's one-shot 1500-player filter, so this pages. `limit` is
        therefore a bandwidth decision, not a display one: the waivers screen ranks by
        upgrade-over-incumbent and shows tens of rows, so the deep tail of a ~1000-player
        pool costs requests nobody reads. Sorting by `AR` (Yahoo's own actual-rank) means
        the cut falls at the bottom of the pool, not somewhere arbitrary.

        `status=A` is available-only — free agents and waivers. Unlike ESPN's filter this
        does not also pull rostered players for their season projection, because Yahoo
        publishes no season projection at all; that axis comes from the independent
        projection source for both sides (see `fantasy_service.get_waivers`).
        """
        items: list[dict] = []
        for start in range(0, limit, PLAYER_POOL_PAGE):
            count = min(PLAYER_POOL_PAGE, limit - start)
            raw = await self._cached_get(
                session,
                endpoint="player_pool",
                cache_params={"league_key": league_key, "start": start, "count": count},
                path=(
                    f"/league/{league_key}/players;status=A;sort=AR"
                    f";start={start};count={count}/percent_owned"
                ),
                ttl=PLAYER_POOL_TTL,
            )
            league_array = raw["fantasy_content"]["league"]
            try:
                players_root = find_subresource(league_array, "players")
            except KeyError:
                break
            page = collection_items(players_root)
            items.extend(page)
            # A short page means the pool ran out before `limit` did.
            if len(page) < count:
                break
        return items
