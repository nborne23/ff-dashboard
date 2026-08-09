"""Yahoo Fantasy OAuth 2.0: authorization URL, CSRF `state`, token exchange + refresh."""

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx

from backend.gridiron.config import Settings

AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
SCOPE = "fspt-r"

STATE_MAX_AGE_SECONDS = 600  # 10 minutes


def redirect_uri(settings: Settings) -> str:
    return settings.gridiron_base_url.rstrip("/") + "/api/connections/yahoo/callback"


def _sign(secret_key: str, payload: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_state(secret_key: str) -> str:
    """Build an HMAC-signed, timestamped CSRF `state` token: `{ts}.{nonce}.{sig}`."""
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(8)
    payload = f"{timestamp}.{nonce}"
    signature = _sign(secret_key, payload)
    return f"{payload}.{signature}"


def verify_state(state: str, secret_key: str, max_age_seconds: int = STATE_MAX_AGE_SECONDS) -> bool:
    """Verify a `state` token's signature and that it's no older than `max_age_seconds`."""
    parts = state.split(".")
    if len(parts) != 3:
        return False
    timestamp, nonce, signature = parts
    payload = f"{timestamp}.{nonce}"
    expected = _sign(secret_key, payload)
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        issued_at = int(timestamp)
    except ValueError:
        return False
    return (time.time() - issued_at) <= max_age_seconds


def build_authorization_url(settings: Settings) -> tuple[str, str]:
    """Return `(authorization_url, state)`. The caller is expected to hand `state` back to
    the browser via the redirect; no server-side state storage is needed since `state` is
    self-verifying (HMAC-signed + timestamped)."""
    state = build_state(settings.gridiron_secret_key)
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", state


async def exchange_code(settings: Settings, code: str) -> dict:
    """Exchange an authorization `code` for an access/refresh token pair."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": redirect_uri(settings),
                "code": code,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(settings: Settings, refresh_token: str) -> dict:
    """Exchange a stored `refresh_token` for a fresh access/refresh token pair."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.yahoo_client_id,
                "client_secret": settings.yahoo_client_secret,
                "redirect_uri": redirect_uri(settings),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()
