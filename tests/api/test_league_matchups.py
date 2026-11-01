"""`/api/teams/{team_id}/league/matchups*` — envelope, Cache-Control, week defaulting,
URL-encoded matchup ids, and typed 404s."""

from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base
from backend.gridiron.services import fantasy_service
from backend.main import app
from tests.services.test_league_matchups import T2, _seed_league

CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "league-matchups-api.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(db) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


def _path(*parts: str) -> str:
    return "/api/teams/" + "/".join(quote(p, safe="") for p in parts)


@pytest.mark.asyncio
async def test_list_defaults_to_the_current_week(client, db) -> None:
    await _seed_league(db)

    response = await client.get(_path(T2, "league", "matchups"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == CACHE_CONTROL
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["week"] == 8
    assert [m["matchup"]["id"] for m in body["data"]["matchups"]] == [
        "yahoo:461.l.123456.mu.8",
        "yahoo:461.l.123456.mu.8.3v4",
    ]
    first = body["data"]["matchups"][0]
    assert first["is_user_matchup"] is True
    assert set(first["home"]) == {"team", "position", "remaining", "is_live"}


@pytest.mark.asyncio
async def test_list_for_an_explicit_week(client, db) -> None:
    await _seed_league(db)

    response = await client.get(_path(T2, "league", "matchups") + "?week=7")

    assert response.status_code == 200
    assert [m["matchup"]["id"] for m in response.json()["data"]["matchups"]] == [
        "yahoo:461.l.123456.mu.7"
    ]


@pytest.mark.asyncio
async def test_list_unknown_team_is_a_typed_404(client) -> None:
    response = await client.get(_path("yahoo:nope", "league", "matchups"))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "team_not_found"


@pytest.mark.asyncio
async def test_detail_by_encoded_matchup_id(client, db) -> None:
    await _seed_league(db)

    response = await client.get(_path(T2, "league", "matchups", "yahoo:461.l.123456.mu.8.3v4"))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["week"] == 8
    assert data["home"]["team"]["name"] == "HellFire Club"
    assert [s["slot"] for s in data["slots"]] == ["QB", "RB1"]


@pytest.mark.asyncio
async def test_detail_unknown_matchup_is_a_typed_404(client, db) -> None:
    await _seed_league(db)

    response = await client.get(_path(T2, "league", "matchups", "yahoo:461.l.123456.mu.99"))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "matchup_not_found"


@pytest.mark.asyncio
async def test_the_standings_route_is_unaffected(client, db) -> None:
    await _seed_league(db)

    response = await client.get(_path(T2, "league"))

    assert response.status_code == 200
    assert len(response.json()["data"]["rows"]) == 4
