"""`YahooClient`'s cache-checked fetch methods: discovery (game key, leagues, team) and raw
roster/matchup fetches. Verifies exact endpoint paths/params (per the platform-integrations
spec), cache-miss-then-hit behavior (respx call counts), and TTL-by-endpoint-class."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.config import Settings
from backend.gridiron.db import make_engine
from backend.gridiron.models import Base
from backend.gridiron.platforms.yahoo.client import BASE_URL, YahooClient
from backend.gridiron.services import cache as cache_service

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "yahoo"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def make_settings() -> Settings:
    return Settings(
        gridiron_secret_key="test-secret",
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        gridiron_base_url="http://localhost:8000",
    )


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "yahoo-cache.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def client():
    c = YahooClient(make_settings(), access_token="at", refresh_token="rt")
    yield c


# --- resolve_game_key ------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_resolve_game_key_picks_highest_season_and_caches(session_factory, client) -> None:
    route = respx.get(
        f"{BASE_URL}/users;use_login=1/games;game_codes=nfl", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("games.json")))

    async with session_factory() as session:
        game_key = await client.resolve_game_key(session)
    assert game_key == "461"
    assert route.call_count == 1

    async with session_factory() as session:
        game_key_again = await client.resolve_game_key(session)
    assert game_key_again == "461"
    assert route.call_count == 1  # second call served from cache, no upstream hit

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_resolve_game_key_caches_for_24_hours(session_factory, client) -> None:
    respx.get(f"{BASE_URL}/users;use_login=1/games;game_codes=nfl", params={"format": "json"}).mock(
        return_value=httpx.Response(200, json=load_fixture("games.json"))
    )

    async with session_factory() as session:
        await client.resolve_game_key(session)

    async with session_factory() as session:
        entry = await cache_service.get(session, "yahoo", "games", None)
        assert entry is not None
        assert entry.expires_at - entry.fetched_at == timedelta(hours=24)

    await client.aclose()


# --- list_leagues ------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_list_leagues_returns_tuples_and_caches(session_factory, client) -> None:
    route = respx.get(
        f"{BASE_URL}/users;use_login=1/games;game_keys=461/leagues", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("leagues.json")))

    async with session_factory() as session:
        leagues = await client.list_leagues(session, "461")
    assert leagues == [
        ("461.l.123456", "The League of Extraordinary Gentlemen", 10, "head"),
        ("461.l.654321", "Dynasty Warriors", 12, "point"),
    ]
    assert route.call_count == 1

    async with session_factory() as session:
        await client.list_leagues(session, "461")
    assert route.call_count == 1  # cache hit

    await client.aclose()


# --- get_team ------------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_team_finds_owned_team_and_caches(session_factory, client) -> None:
    route = respx.get(f"{BASE_URL}/league/461.l.123456/teams", params={"format": "json"}).mock(
        return_value=httpx.Response(200, json=load_fixture("teams.json"))
    )

    async with session_factory() as session:
        team_key = await client.get_team(session, "461.l.123456")
    assert team_key == "461.l.123456.t.1"
    assert route.call_count == 1

    async with session_factory() as session:
        await client.get_team(session, "461.l.123456")
    assert route.call_count == 1  # cache hit

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_team_raises_when_no_owned_team_found(session_factory, client) -> None:
    unowned = load_fixture("teams.json")
    for team_item in unowned["fantasy_content"]["league"][1]["teams"].values():
        if isinstance(team_item, dict):
            team_item["team"][0][-1]["is_owned_by_current_login"] = 0

    respx.get(f"{BASE_URL}/league/461.l.123456/teams", params={"format": "json"}).mock(
        return_value=httpx.Response(200, json=unowned)
    )

    async with session_factory() as session:
        with pytest.raises(ValueError, match="no team owned"):
            await client.get_team(session, "461.l.123456")

    await client.aclose()


# --- get_roster ------------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_returns_raw_json_and_caches(session_factory, client) -> None:
    fixture = load_fixture("roster.json")
    route = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=14/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=fixture))

    async with session_factory() as session:
        raw = await client.get_roster(session, "461.l.123456.t.1", 14)
    assert raw == fixture
    assert route.call_count == 1

    async with session_factory() as session:
        raw_again = await client.get_roster(session, "461.l.123456.t.1", 14)
    assert raw_again == fixture
    assert route.call_count == 1  # cache hit, no second upstream call

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_expired_cache_refetches(session_factory, client) -> None:
    fixture = load_fixture("roster.json")
    route = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=14/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=fixture))

    async with session_factory() as session:
        await cache_service.set(
            session,
            "yahoo",
            "roster",
            {"team_key": "461.l.123456.t.1", "week": 14},
            "{}",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    async with session_factory() as session:
        raw = await client.get_roster(session, "461.l.123456.t.1", 14)
    assert raw == fixture
    assert route.call_count == 1  # stale cache entry triggers a fresh upstream fetch

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_caches_for_1_hour_off_day_default(session_factory, client) -> None:
    respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=14/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("roster.json")))

    async with session_factory() as session:
        await client.get_roster(session, "461.l.123456.t.1", 14)

    async with session_factory() as session:
        entry = await cache_service.get(
            session, "yahoo", "roster", {"team_key": "461.l.123456.t.1", "week": 14}
        )
        assert entry is not None
        assert entry.expires_at - entry.fetched_at == timedelta(hours=1)

    await client.aclose()


# --- get_matchup ------------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_matchup_returns_raw_json_and_caches(session_factory, client) -> None:
    fixture = load_fixture("matchup.json")
    route = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/matchups;weeks=14", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=fixture))

    async with session_factory() as session:
        raw = await client.get_matchup(session, "461.l.123456.t.1", 14)
    assert raw == fixture
    assert route.call_count == 1

    async with session_factory() as session:
        raw_again = await client.get_matchup(session, "461.l.123456.t.1", 14)
    assert raw_again == fixture
    assert route.call_count == 1  # cache hit

    await client.aclose()


# --- week plumbing / past-week TTL (tasks 9.3 / 9.5) ---------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_url_reflects_a_non_current_requested_week(
    session_factory, client
) -> None:
    """9.3: `week` isn't hardcoded anywhere in the client — the upstream URL/params always
    reflect whatever week is requested, current or not."""
    route = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=5/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("roster.json")))

    async with session_factory() as session:
        await client.get_roster(session, "461.l.123456.t.1", 5)

    assert route.call_count == 1
    assert "week=5" in str(route.calls.last.request.url)


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_uses_24h_ttl_for_a_week_well_in_the_past(session_factory, client) -> None:
    respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=5/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("roster.json")))

    async with session_factory() as session:
        await client.get_roster(session, "461.l.123456.t.1", 5, current_week=14)

    async with session_factory() as session:
        entry = await cache_service.get(
            session, "yahoo", "roster", {"team_key": "461.l.123456.t.1", "week": 5}
        )
        assert entry is not None
        assert entry.expires_at - entry.fetched_at == timedelta(hours=24)

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_keeps_1h_default_when_week_is_still_current(
    session_factory, client
) -> None:
    respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/roster;week=14/players/stats", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=load_fixture("roster.json")))

    async with session_factory() as session:
        await client.get_roster(session, "461.l.123456.t.1", 14, current_week=14)

    async with session_factory() as session:
        entry = await cache_service.get(
            session, "yahoo", "roster", {"team_key": "461.l.123456.t.1", "week": 14}
        )
        assert entry is not None
        assert entry.expires_at - entry.fetched_at == timedelta(hours=1)


@pytest.mark.asyncio
@respx.mock
async def test_get_matchup_uses_24h_ttl_for_a_week_well_in_the_past(
    session_factory, client
) -> None:
    respx.get(f"{BASE_URL}/team/461.l.123456.t.1/matchups;weeks=5", params={"format": "json"}).mock(
        return_value=httpx.Response(200, json=load_fixture("matchup.json"))
    )

    async with session_factory() as session:
        await client.get_matchup(session, "461.l.123456.t.1", 5, current_week=14)

    async with session_factory() as session:
        entry = await cache_service.get(
            session, "yahoo", "matchup", {"team_key": "461.l.123456.t.1", "week": 5}
        )
        assert entry is not None
        assert entry.expires_at - entry.fetched_at == timedelta(hours=24)


@pytest.mark.asyncio
@respx.mock
async def test_get_matchup_different_weeks_are_cached_separately(session_factory, client) -> None:
    fixture14 = load_fixture("matchup.json")
    fixture15 = load_fixture("matchup.json")
    fixture15["fantasy_content"]["team"][1]["matchups"]["0"]["matchup"]["week"] = "15"

    route14 = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/matchups;weeks=14", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=fixture14))
    route15 = respx.get(
        f"{BASE_URL}/team/461.l.123456.t.1/matchups;weeks=15", params={"format": "json"}
    ).mock(return_value=httpx.Response(200, json=fixture15))

    async with session_factory() as session:
        await client.get_matchup(session, "461.l.123456.t.1", 14)
        await client.get_matchup(session, "461.l.123456.t.1", 15)

    assert route14.call_count == 1
    assert route15.call_count == 1

    await client.aclose()
