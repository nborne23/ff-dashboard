"""`GET /api/highlights` — cursor semantics and the replay window (add-play-highlights)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.api.highlights import REPLAY_WINDOW
from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, Player, PlayerHighlight
from backend.gridiron.services import fantasy_service
from backend.main import app


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "highlights-api.db")
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


def _highlight(ordinal: int, created_at: datetime) -> PlayerHighlight:
    return PlayerHighlight(
        sleeper_id="100",
        player_id="yahoo:461.p.30123",
        season=2026,
        week=8,
        kind="touchdown",
        stat_key="rec_td",
        ordinal=ordinal,
        yards=34,
        stat_line="4 rec · 62 yds · 1 TD",
        created_at=created_at,
    )


async def _seed(db, *highlights: PlayerHighlight) -> None:
    async with db() as session:
        session.add(
            Player(
                id="yahoo:461.p.30123",
                platform="yahoo",
                platform_id="461.p.30123",
                name="Patrick Mahomes",
                position="QB",
                nfl_team="KC",
                nfl_opponent=None,
                nfl_game_id=None,
                bye_week=None,
                injury_status=None,
            )
        )
        session.add_all(highlights)
        await session.commit()


@pytest.mark.asyncio
async def test_empty_table(client) -> None:
    body = (await client.get("/api/highlights")).json()
    assert body["data"] == {"highlights": [], "latest_id": None}


@pytest.mark.asyncio
async def test_without_cursor_returns_only_the_cursor(db, client) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    await _seed(db, _highlight(1, now), _highlight(2, now))

    response = await client.get("/api/highlights")

    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {"highlights": [], "latest_id": 2}


@pytest.mark.asyncio
async def test_after_cursor_returns_newer_with_display_fields(db, client) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    await _seed(db, _highlight(1, now), _highlight(2, now))

    data = (await client.get("/api/highlights", params={"after": 1})).json()["data"]

    assert data["latest_id"] == 2
    [only] = data["highlights"]
    assert only["id"] == 2
    assert only["player_name"] == "Patrick Mahomes"
    assert only["headshot_url"] == "/api/headshots/yahoo/30123.png"
    assert only["yards"] == 34


@pytest.mark.asyncio
async def test_old_highlights_are_not_replayed(db, client) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    await _seed(db, _highlight(1, now - REPLAY_WINDOW - timedelta(minutes=1)))

    data = (await client.get("/api/highlights", params={"after": 0})).json()["data"]

    assert data == {"highlights": [], "latest_id": 1}
