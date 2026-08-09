"""`/api/admin` — manual refresh trigger runs the job coroutine (scheduler off) and records
`refresh_runs` rows for both success and failure."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, RefreshRun
from backend.gridiron.services import fantasy_service
from backend.main import app


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "admin-api.db")
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
async def test_refresh_runs_discovery_and_records_ok_run(client, db) -> None:
    # No connections in the DB: discovery is a clean no-op and the run succeeds.
    response = await client.post("/api/admin/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["job_name"] == "sync_discovery"
    assert body["ok"] is True
    assert body["error"] is None
    assert body["duration_ms"] >= 0

    async with db() as session:
        runs = (await session.execute(select(RefreshRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].job_name == "sync_discovery"
    assert runs[0].ok is True


@pytest.mark.asyncio
async def test_refresh_failure_is_recorded_not_raised(client, db, monkeypatch) -> None:
    async def boom(session, settings=None):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(fantasy_service, "refresh_discovery", boom)

    response = await client.post("/api/admin/refresh?job=sync_discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "upstream exploded" in body["error"]

    async with db() as session:
        runs = (await session.execute(select(RefreshRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].ok is False
    assert "upstream exploded" in runs[0].error


@pytest.mark.asyncio
async def test_refresh_platform_error_summary_recorded_on_run(client, db, monkeypatch) -> None:
    async def partial_failure(session, settings=None):
        return {
            "yahoo": fantasy_service.PlatformOutcome(ok=False, error="auth_required"),
            "espn": fantasy_service.PlatformOutcome(ok=True),
        }

    monkeypatch.setattr(fantasy_service, "refresh_discovery", partial_failure)

    response = await client.post("/api/admin/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "yahoo: auth_required"


@pytest.mark.asyncio
async def test_refresh_unknown_job_returns_typed_400(client) -> None:
    response = await client.post("/api/admin/refresh?job=bogus")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_job"


@pytest.mark.asyncio
async def test_refresh_runs_lists_recent_runs_newest_first(client, db) -> None:
    await client.post("/api/admin/refresh")
    await client.post("/api/admin/refresh")

    response = await client.get("/api/admin/refresh-runs?limit=20")

    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 2
    assert runs[0]["id"] > runs[1]["id"]
    assert all(r["job_name"] == "sync_discovery" for r in runs)


@pytest.mark.asyncio
async def test_refresh_runs_respects_limit(client) -> None:
    for _ in range(3):
        await client.post("/api/admin/refresh")

    response = await client.get("/api/admin/refresh-runs?limit=2")

    assert len(response.json()) == 2
