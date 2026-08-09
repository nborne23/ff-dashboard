"""`/api/settings` — server-persisted live-refresh tier (task 7.4) plus the Phase 8
seam it now fills in: rescheduling `refresh_fantasy` and publishing `tier.change` on
every `POST /api/settings/live-tier` (task 8.3)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base
from backend.gridiron.services import events
from backend.main import app


@pytest.fixture(autouse=True)
def _reset_module_state():
    events.reset()
    yield
    events.reset()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "settings-api.db")
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
async def test_get_settings_defaults_to_30s(client) -> None:
    response = await client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"live_tier": "30s"}


@pytest.mark.asyncio
async def test_post_live_tier_persists_and_get_reflects_it(client) -> None:
    response = await client.post("/api/settings/live-tier", json={"live_tier": "10s"})

    assert response.status_code == 200
    assert response.json() == {"live_tier": "10s"}

    again = await client.get("/api/settings")
    assert again.json() == {"live_tier": "10s"}


@pytest.mark.asyncio
async def test_post_live_tier_upserts_on_repeat_calls(client) -> None:
    await client.post("/api/settings/live-tier", json={"live_tier": "10s"})
    response = await client.post("/api/settings/live-tier", json={"live_tier": "1m"})

    assert response.status_code == 200
    assert response.json() == {"live_tier": "1m"}

    again = await client.get("/api/settings")
    assert again.json() == {"live_tier": "1m"}


@pytest.mark.asyncio
async def test_post_live_tier_rejects_unknown_value(client) -> None:
    response = await client.post("/api/settings/live-tier", json={"live_tier": "5s"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_live_tier_publishes_tier_change_event(client) -> None:
    queue = events.subscribe()

    response = await client.post("/api/settings/live-tier", json={"live_tier": "10s"})

    assert response.status_code == 200
    event = queue.get_nowait()
    assert event.type == "tier.change"
    assert event.live_tier_seconds == 10


@pytest.mark.asyncio
async def test_post_live_tier_1m_publishes_60_seconds(client) -> None:
    queue = events.subscribe()

    await client.post("/api/settings/live-tier", json={"live_tier": "1m"})

    event = queue.get_nowait()
    assert event.live_tier_seconds == 60


@pytest.mark.asyncio
async def test_post_live_tier_does_not_raise_when_scheduler_is_not_running(client) -> None:
    # dev default (GRIDIRON_SCHEDULER_ENABLED=false, no test starts the scheduler) —
    # scheduler.reschedule_refresh_fantasy must no-op rather than error.
    response = await client.post("/api/settings/live-tier", json={"live_tier": "30s"})
    assert response.status_code == 200
