"""`/api/leagues` — list (both platforms, plain list) + per-league enable toggle (task 7.3)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, League
from backend.main import app

ESPN_LEAGUE = "espn:1234567"
YAHOO_LEAGUE = "yahoo:461.l.123456"


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "leagues-api.db")
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


async def seed(db) -> None:
    async with db() as session:
        session.add(
            League(
                id=ESPN_LEAGUE,
                platform="espn",
                platform_id="1234567",
                name="Highland Bombers League",
                season=2024,
                team_count=10,
                scoring_type="ppr",
                current_week=9,
            )
        )
        session.add(
            League(
                id=YAHOO_LEAGUE,
                platform="yahoo",
                platform_id="461.l.123456",
                name="The League of Extraordinary Gentlemen",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=14,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_list_leagues_returns_both_platforms_enabled_by_default(client, db) -> None:
    await seed(db)

    response = await client.get("/api/leagues")

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {ESPN_LEAGUE, YAHOO_LEAGUE}
    assert all(row["is_enabled"] is True for row in body)
    espn_row = next(row for row in body if row["id"] == ESPN_LEAGUE)
    assert espn_row["platform"] == "espn"
    assert espn_row["team_count"] == 10
    assert espn_row["scoring_type"] == "ppr"
    assert espn_row["season"] == 2024


@pytest.mark.asyncio
async def test_list_leagues_empty_db_returns_empty_list(client) -> None:
    response = await client.get("/api/leagues")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_patch_league_disables_it(client, db) -> None:
    await seed(db)

    response = await client.patch(f"/api/leagues/{ESPN_LEAGUE}", json={"is_enabled": False})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ESPN_LEAGUE
    assert body["is_enabled"] is False

    # Persisted, not just echoed back.
    again = await client.get("/api/leagues")
    espn_row = next(row for row in again.json() if row["id"] == ESPN_LEAGUE)
    assert espn_row["is_enabled"] is False


@pytest.mark.asyncio
async def test_patch_league_re_enables_it(client, db) -> None:
    await seed(db)
    await client.patch(f"/api/leagues/{ESPN_LEAGUE}", json={"is_enabled": False})

    response = await client.patch(f"/api/leagues/{ESPN_LEAGUE}", json={"is_enabled": True})

    assert response.status_code == 200
    assert response.json()["is_enabled"] is True


@pytest.mark.asyncio
async def test_patch_unknown_league_returns_typed_404(client) -> None:
    response = await client.patch("/api/leagues/espn:nope", json={"is_enabled": False})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "league_not_found"
