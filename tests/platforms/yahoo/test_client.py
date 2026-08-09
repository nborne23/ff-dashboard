from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx

from backend.gridiron.config import Settings
from backend.gridiron.errors import AuthRequiredError, RateLimitedError
from backend.gridiron.platforms.yahoo.client import BASE_URL, YahooClient


def make_settings() -> Settings:
    return Settings(
        gridiron_secret_key="test-secret",
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        gridiron_base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
@respx.mock
async def test_401_triggers_refresh_then_retries_original_request() -> None:
    settings = make_settings()
    refreshed = AsyncMock()

    respx.get(f"{BASE_URL}/some/path").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    respx.post("https://api.login.yahoo.com/oauth2/get_token").mock(
        return_value=httpx.Response(200, json={"access_token": "new-at", "refresh_token": "new-rt"})
    )

    client = YahooClient(
        settings, access_token="old-at", refresh_token="old-rt", on_token_refresh=refreshed
    )
    response = await client.get("/some/path")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    refreshed.assert_awaited_once_with("new-at", "new-rt")
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_failure_raises_auth_required_error() -> None:
    settings = make_settings()

    respx.get(f"{BASE_URL}/some/path").mock(return_value=httpx.Response(401))
    respx.post("https://api.login.yahoo.com/oauth2/get_token").mock(
        return_value=httpx.Response(400)
    )

    client = YahooClient(settings, access_token="old-at", refresh_token="old-rt")

    with pytest.raises(AuthRequiredError):
        await client.get("/some/path")
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_429_backs_off_exponentially_then_raises_rate_limited() -> None:
    settings = make_settings()
    respx.get(f"{BASE_URL}/some/path").mock(return_value=httpx.Response(429))

    client = YahooClient(settings, access_token="at", refresh_token="rt")

    with patch(
        "backend.gridiron.platforms.yahoo.client.asyncio.sleep", new=AsyncMock()
    ) as sleep_mock:
        with pytest.raises(RateLimitedError):
            await client.get("/some/path")

    assert sleep_mock.await_args_list == [call(1), call(2), call(4)]
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_999_also_triggers_backoff_and_recovers() -> None:
    settings = make_settings()
    respx.get(f"{BASE_URL}/some/path").mock(
        side_effect=[
            httpx.Response(999),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    client = YahooClient(settings, access_token="at", refresh_token="rt")

    with patch(
        "backend.gridiron.platforms.yahoo.client.asyncio.sleep", new=AsyncMock()
    ) as sleep_mock:
        response = await client.get("/some/path")

    assert response.status_code == 200
    sleep_mock.assert_awaited_once_with(1)
    await client.aclose()
