import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.config import Settings
from backend.gridiron.db import make_engine
from backend.gridiron.errors import AuthRequiredError
from backend.gridiron.models import Base
from backend.gridiron.platforms.espn.client import EspnClient
from backend.gridiron.services import cache

BASE_URL = "https://lm-api-reads.fantasy.espn.com"
LEAGUE_PATH = "/apis/v3/games/ffl/seasons/2025/segments/0/leagues/1234567"


def make_settings() -> Settings:
    return Settings(espn_base_url="https://lm-api-reads.fantasy.espn.com")


@pytest.fixture
async def session_factory(tmp_path):
    """Mirrors `tests/services/test_cache.py`'s fixture — a throwaway sqlite DB per test."""
    engine = make_engine(tmp_path / "espn-client.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def make_client(session_factory) -> EspnClient:
    return EspnClient(
        make_settings(), swid="{ABC-123}", espn_s2="s2-value", session_factory=session_factory
    )


@pytest.mark.asyncio
@respx.mock
async def test_sends_swid_and_espn_s2_cookie_header() -> None:
    settings = make_settings()
    route = respx.get("https://lm-api-reads.fantasy.espn.com/some/path").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    client = EspnClient(settings, swid="{ABC-123}", espn_s2="s2-value")
    response = await client.get("/some/path")

    assert response.status_code == 200
    sent = route.calls.last.request
    assert sent.headers["Cookie"] == "SWID={ABC-123}; espn_s2=s2-value"
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_required_error() -> None:
    settings = make_settings()
    respx.get("https://lm-api-reads.fantasy.espn.com/some/path").mock(
        return_value=httpx.Response(401)
    )

    client = EspnClient(settings, swid="{ABC-123}", espn_s2="s2-value")
    with pytest.raises(AuthRequiredError):
        await client.get("/some/path")
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_403_raises_auth_required_error() -> None:
    settings = make_settings()
    respx.get("https://lm-api-reads.fantasy.espn.com/some/path").mock(
        return_value=httpx.Response(403)
    )

    client = EspnClient(settings, swid="{ABC-123}", espn_s2="s2-value")
    with pytest.raises(AuthRequiredError):
        await client.get("/some/path")
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_probe_league_hits_expected_endpoint() -> None:
    settings = make_settings()
    route = respx.get(
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leagues"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))

    client = EspnClient(settings, swid="{ABC-123}", espn_s2="s2-value")
    response = await client.probe_league(2025)

    assert response.status_code == 200
    assert route.calls.last.request.url.params["view"] == "mTeam"
    await client.aclose()


# --- get_league --------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_league_stacks_view_params_and_returns_parsed_json(session_factory) -> None:
    league_body = {"id": 1234567, "settings": {"name": "Test League"}}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(
        return_value=httpx.Response(200, json=league_body)
    )

    client = make_client(session_factory)
    result = await client.get_league(1234567, 2025)

    assert result == league_body
    sent_views = [v for k, v in route.calls.last.request.url.params.multi_items() if k == "view"]
    assert sent_views == ["mSettings", "mTeam"]
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_league_cache_miss_fetches_and_stores(session_factory) -> None:
    league_body = {"id": 1234567, "settings": {"name": "Test League"}}
    respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=league_body))

    client = make_client(session_factory)
    async with session_factory() as session:
        before = await cache.get(
            session,
            "espn",
            "league",
            {"view": ["mSettings", "mTeam"], "league_id": 1234567, "year": 2025},
        )
    assert before is None

    result = await client.get_league(1234567, 2025)
    assert result == league_body

    async with session_factory() as session:
        after = await cache.get(
            session,
            "espn",
            "league",
            {"view": ["mSettings", "mTeam"], "league_id": 1234567, "year": 2025},
        )
    assert after is not None
    assert json.loads(after.raw_json) == league_body
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_league_fresh_cache_hit_makes_no_upstream_call(session_factory) -> None:
    league_body = {"id": 1234567, "settings": {"name": "Test League"}}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(
        return_value=httpx.Response(200, json=league_body)
    )

    client = make_client(session_factory)
    first = await client.get_league(1234567, 2025)
    assert route.call_count == 1

    second = await client.get_league(1234567, 2025)
    assert route.call_count == 1  # no additional upstream call on the fresh hit
    assert second == first
    await client.aclose()


# --- get_roster / get_matchup --------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_stacks_expected_views_and_periods(session_factory) -> None:
    body = {"id": 1234567, "schedule": []}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    client = make_client(session_factory)
    result = await client.get_roster(1234567, 2025, scoring_period=10)

    assert result == body
    sent = route.calls.last.request.url.params
    sent_views = [v for k, v in sent.multi_items() if k == "view"]
    assert sent_views == ["mRoster", "mMatchupScore", "mBoxscore"]
    assert sent["scoringPeriodId"] == "10"
    assert sent["matchupPeriodId"] == "10"
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_and_get_matchup_share_one_cache_entry(session_factory) -> None:
    body = {"id": 1234567, "schedule": []}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    client = make_client(session_factory)
    roster = await client.get_roster(1234567, 2025, scoring_period=10)
    matchup = await client.get_matchup(1234567, 2025, scoring_period=10)

    assert roster == matchup == body
    assert route.call_count == 1  # get_matchup served from the cache get_roster populated
    await client.aclose()


# --- week plumbing / past-week TTL (tasks 9.3 / 9.5) ---------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_url_reflects_a_non_current_requested_week(session_factory) -> None:
    """9.3: `scoring_period` isn't hardcoded anywhere in the client — the upstream
    `scoringPeriodId`/`matchupPeriodId` params always reflect whatever week is
    requested, current or not (companion to `test_get_roster_stacks_expected_views_and_
    periods`, which already covers this for week=10 — this pins a different value)."""
    body = {"id": 1234567, "schedule": []}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    client = make_client(session_factory)
    await client.get_roster(1234567, 2025, scoring_period=5)

    sent = route.calls.last.request.url.params
    assert sent["scoringPeriodId"] == "5"
    assert sent["matchupPeriodId"] == "5"
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_uses_24h_ttl_for_a_week_well_in_the_past(session_factory) -> None:
    body = {"id": 1234567, "schedule": []}
    respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    client = make_client(session_factory)
    await client.get_roster(1234567, 2025, scoring_period=5, current_week=10)

    async with session_factory() as session:
        entry = await cache.get(
            session,
            "espn",
            "roster_matchup",
            {
                "view": ["mRoster", "mMatchupScore", "mBoxscore"],
                "scoringPeriodId": 5,
                "matchupPeriodId": 5,
                "league_id": 1234567,
                "year": 2025,
            },
        )
    assert entry is not None
    assert entry.expires_at - entry.fetched_at == timedelta(hours=24)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_keeps_1h_default_when_week_is_still_current(session_factory) -> None:
    body = {"id": 1234567, "schedule": []}
    respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    client = make_client(session_factory)
    await client.get_roster(1234567, 2025, scoring_period=10, current_week=10)

    async with session_factory() as session:
        entry = await cache.get(
            session,
            "espn",
            "roster_matchup",
            {
                "view": ["mRoster", "mMatchupScore", "mBoxscore"],
                "scoringPeriodId": 10,
                "matchupPeriodId": 10,
                "league_id": 1234567,
                "year": 2025,
            },
        )
    assert entry is not None
    assert entry.expires_at - entry.fetched_at == timedelta(hours=1)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_roster_expired_cache_refetches(session_factory) -> None:
    body = {"id": 1234567, "schedule": [{"stale": False}]}
    route = respx.get(f"{BASE_URL}{LEAGUE_PATH}").mock(return_value=httpx.Response(200, json=body))

    async with session_factory() as session:
        await cache.set(
            session,
            "espn",
            "roster_matchup",
            {
                "view": ["mRoster", "mMatchupScore", "mBoxscore"],
                "scoringPeriodId": 10,
                "matchupPeriodId": 10,
                "league_id": 1234567,
                "year": 2025,
            },
            json.dumps({"id": 1234567, "schedule": [{"stale": True}]}),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    client = make_client(session_factory)
    result = await client.get_roster(1234567, 2025, scoring_period=10)

    assert result == body  # refetched, not the stale cached payload
    assert route.call_count == 1
    await client.aclose()
