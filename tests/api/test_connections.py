from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base
from backend.gridiron.platforms.yahoo import oauth
from backend.main import app

TEST_SECRET_KEY = "test-secret-key"
CURRENT_YEAR = datetime.now(UTC).year


def make_test_settings() -> Settings:
    return Settings(
        gridiron_secret_key=TEST_SECRET_KEY,
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        gridiron_base_url="http://localhost:8000",
        espn_base_url="https://lm-api-reads.fantasy.espn.com",
    )


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client against the app with an isolated temp-sqlite DB and test settings."""
    db_path = tmp_path / "test.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    settings = make_test_settings()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_connections_starts_disconnected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/connections")

    assert response.status_code == 200
    body = {row["platform"]: row for row in response.json()}
    assert body["yahoo"]["is_connected"] is False
    assert body["espn"]["is_connected"] is False


@pytest.mark.asyncio
async def test_yahoo_start_returns_auth_url(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/connections/yahoo/start")

    assert response.status_code == 200
    auth_url = response.json()["auth_url"]
    assert auth_url.startswith(oauth.AUTHORIZE_URL)
    assert "state=" in auth_url


@pytest.mark.asyncio
@respx.mock
async def test_yahoo_callback_persists_tokens_and_redirects(client: httpx.AsyncClient) -> None:
    respx.post(oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"})
    )
    state = oauth.build_state(TEST_SECRET_KEY)

    response = await client.get(
        "/api/connections/yahoo/callback",
        params={"code": "the-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "http://localhost:8000/settings"

    status_response = await client.get("/api/connections")
    body = {row["platform"]: row for row in status_response.json()}
    assert body["yahoo"]["is_connected"] is True
    assert body["yahoo"]["last_verified_at"] is not None


@pytest.mark.asyncio
async def test_yahoo_callback_rejects_invalid_state(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/connections/yahoo/callback",
        params={"code": "the-code", "state": "garbage"},
        follow_redirects=False,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_espn_test_happy_path_persists_and_marks_verified(client: httpx.AsyncClient) -> None:
    respx.get(
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{CURRENT_YEAR}/segments/0/leagues"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))

    response = await client.post(
        "/api/connections/espn/test",
        json={"swid": "{ABC-123}", "espn_s2": "s2-value"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_connected"] is True
    assert body["last_verified_at"] is not None


@pytest.mark.asyncio
async def test_espn_test_rejects_malformed_swid(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/connections/espn/test",
        json={"swid": "not-a-swid", "espn_s2": "s2-value"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_espn_test_rejects_on_espn_401(client: httpx.AsyncClient) -> None:
    respx.get(
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{CURRENT_YEAR}/segments/0/leagues"
    ).mock(return_value=httpx.Response(401))

    response = await client.post(
        "/api/connections/espn/test",
        json={"swid": "{ABC-123}", "espn_s2": "s2-value"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "auth_required"

    # Rejected credentials must not be persisted.
    status_response = await client.get("/api/connections")
    body = {row["platform"]: row for row in status_response.json()}
    assert body["espn"]["is_connected"] is False


@pytest.mark.asyncio
@respx.mock
async def test_delete_connection_removes_row(client: httpx.AsyncClient) -> None:
    respx.get(
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{CURRENT_YEAR}/segments/0/leagues"
    ).mock(return_value=httpx.Response(200, json={"ok": True}))
    await client.post(
        "/api/connections/espn/test", json={"swid": "{ABC-123}", "espn_s2": "s2-value"}
    )

    response = await client.delete("/api/connections/espn")
    assert response.status_code == 204

    status_response = await client.get("/api/connections")
    body = {row["platform"]: row for row in status_response.json()}
    assert body["espn"]["is_connected"] is False
