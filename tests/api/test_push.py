"""`/api/push/*` routes (add-push-notifications). The network send is replaced."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, PushSubscription
from backend.gridiron.services import push
from backend.main import app

APPLE = "https://web.push.apple.com/QGxyz"
BODY = {"endpoint": APPLE, "keys": {"p256dh": "p", "auth": "a"}, "expirationTime": None}


@pytest.fixture(autouse=True)
def _fake_network(monkeypatch):
    fake = SimpleNamespace(gridiron_secret_key="s", gridiron_base_url="https://imac.ts.net")
    monkeypatch.setattr(push, "get_settings", lambda: fake)
    monkeypatch.setattr(push, "webpush", lambda **_: SimpleNamespace(status_code=201, text=""))


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "push-api.db")
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


async def _endpoints(db) -> list[str]:
    async with db() as session:
        return [s.endpoint for s in (await session.execute(select(PushSubscription))).scalars()]


@pytest.mark.asyncio
async def test_public_key_is_stable(client) -> None:
    first = (await client.get("/api/push/vapid-public-key")).json()["public_key"]
    second = (await client.get("/api/push/vapid-public-key")).json()["public_key"]
    assert first == second and len(first) == 87  # 65 bytes, base64url, unpadded


@pytest.mark.asyncio
async def test_subscribe_test_and_unsubscribe(db, client) -> None:
    assert (await client.post("/api/push/subscriptions", json=BODY)).status_code == 204
    assert (await client.post("/api/push/subscriptions", json=BODY)).status_code == 204
    assert await _endpoints(db) == [APPLE]

    result = (await client.post("/api/push/test")).json()
    assert result == {"subscriptions": 1, "delivered": 1}

    response = await client.request("DELETE", "/api/push/subscriptions", json={"endpoint": APPLE})
    assert response.status_code == 204
    assert await _endpoints(db) == []


@pytest.mark.asyncio
async def test_unknown_push_host_is_rejected(db, client) -> None:
    body = {**BODY, "endpoint": "https://evil.example.com/collect"}
    response = await client.post("/api/push/subscriptions", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_endpoint"
    assert await _endpoints(db) == []
