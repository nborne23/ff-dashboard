import time
from unittest.mock import patch

import httpx
import pytest
import respx

from backend.gridiron.config import Settings
from backend.gridiron.platforms.yahoo import oauth


def make_settings(**overrides) -> Settings:
    defaults = dict(
        gridiron_secret_key="test-secret",
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        gridiron_base_url="http://localhost:8000",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_build_and_verify_state_round_trip() -> None:
    state = oauth.build_state("test-secret")
    assert oauth.verify_state(state, "test-secret") is True


def test_verify_state_rejects_wrong_secret() -> None:
    state = oauth.build_state("test-secret")
    assert oauth.verify_state(state, "other-secret") is False


def test_verify_state_rejects_tampered_payload() -> None:
    state = oauth.build_state("test-secret")
    ts, nonce, sig = state.split(".")
    tampered = f"{ts}.{nonce}x.{sig}"
    assert oauth.verify_state(tampered, "test-secret") is False


def test_verify_state_rejects_malformed_state() -> None:
    assert oauth.verify_state("not-a-valid-state", "test-secret") is False


def test_verify_state_rejects_expired_state() -> None:
    old_timestamp = int(time.time()) - 700  # > 10 minutes old
    with patch("time.time", return_value=old_timestamp):
        state = oauth.build_state("test-secret")

    assert oauth.verify_state(state, "test-secret", max_age_seconds=600) is False


def test_verify_state_accepts_state_within_max_age() -> None:
    recent_timestamp = int(time.time()) - 100
    with patch("time.time", return_value=recent_timestamp):
        state = oauth.build_state("test-secret")

    assert oauth.verify_state(state, "test-secret", max_age_seconds=600) is True


def test_build_authorization_url_contains_expected_params() -> None:
    settings = make_settings()
    url, state = oauth.build_authorization_url(settings)

    assert url.startswith(oauth.AUTHORIZE_URL)
    assert "response_type=code" in url
    assert "scope=fspt-r" in url
    assert "client_id=client-id" in url
    assert f"state={state}" in url
    assert (
        "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fconnections%2Fyahoo%2Fcallback" in url
    )


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_posts_to_token_endpoint() -> None:
    settings = make_settings()
    route = respx.post(oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"})
    )

    tokens = await oauth.exchange_code(settings, "the-code")

    assert route.called
    assert tokens == {"access_token": "at", "refresh_token": "rt"}
    sent = route.calls.last.request
    assert b"grant_type=authorization_code" in sent.content
    assert b"code=the-code" in sent.content


@pytest.mark.asyncio
@respx.mock
async def test_refresh_access_token_posts_to_token_endpoint() -> None:
    settings = make_settings()
    route = respx.post(oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-at", "refresh_token": "new-rt"})
    )

    tokens = await oauth.refresh_access_token(settings, "old-refresh-token")

    assert route.called
    assert tokens["access_token"] == "new-at"
    sent = route.calls.last.request
    assert b"grant_type=refresh_token" in sent.content
    assert b"refresh_token=old-refresh-token" in sent.content
