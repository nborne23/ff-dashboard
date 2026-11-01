"""`GET /api/scores` and `GET /api/scores/games/{game_id}` (add-nfl-scores)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base
from backend.gridiron.services import fantasy_service
from backend.main import app
from tests.services.test_scores import FINAL_GAME, seed


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "scores-api.db")
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


@pytest.mark.asyncio
async def test_scores_on_an_empty_database(client) -> None:
    response = await client.get("/api/scores")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["games"] == []
    assert body["data"]["fetched_at"] is None
    assert "live_state" in body["meta"]


@pytest.mark.asyncio
async def test_scores_for_the_current_week(client, db) -> None:
    async with db() as session:
        await seed(session)

    data = (await client.get("/api/scores")).json()["data"]

    assert (data["season"], data["week"], data["current_week"]) == (2025, 7, 7)
    assert len(data["games"]) == 4
    final = next(g for g in data["games"] if g["game_id"] == FINAL_GAME)
    assert final["home"]["abbr"] == "CIN" and final["home"]["score"] == 33
    # Tz-aware, so the browser reads kickoff as UTC rather than local time.
    assert final["kickoff_at"].endswith("Z") or final["kickoff_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_scores_week_is_bounded(client) -> None:
    assert (await client.get("/api/scores", params={"week": 0})).status_code == 422
    assert (await client.get("/api/scores", params={"week": 19})).status_code == 422


@pytest.mark.asyncio
async def test_game_detail(client, db) -> None:
    async with db() as session:
        await seed(session)

    response = await client.get(f"/api/scores/games/{FINAL_GAME}", params={"league_id": "espn:1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["league_id"] == "espn:1"
    assert data["game"]["status_text"] == "Final"
    qb = data["groups"][0]
    assert qb["position"] == "QB"
    assert qb["home"][0]["short_name"] == "J. Flacco"
    assert qb["home"][0]["source"] == "league"


@pytest.mark.asyncio
async def test_unknown_league_falls_back_to_the_first(client, db) -> None:
    async with db() as session:
        await seed(session)

    data = (
        await client.get(f"/api/scores/games/{FINAL_GAME}", params={"league_id": "nope"})
    ).json()["data"]

    assert data["league_id"] == "espn:1"


@pytest.mark.asyncio
async def test_unknown_game_is_404(client, db) -> None:
    async with db() as session:
        await seed(session)

    assert (await client.get("/api/scores/games/123")).status_code == 404
