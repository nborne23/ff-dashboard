"""`/api/connections` — Yahoo OAuth + ESPN cookie connection management."""

import re
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session
from backend.gridiron.errors import AuthRequiredError
from backend.gridiron.models import Connection
from backend.gridiron.platforms.espn.client import EspnClient
from backend.gridiron.platforms.yahoo import oauth
from backend.gridiron.services import credentials

router = APIRouter(prefix="/api/connections", tags=["connections"])

SWID_PATTERN = re.compile(r"^\{[0-9A-Fa-f-]+\}$")

Platform = Literal["yahoo", "espn"]
PLATFORMS: tuple[Platform, ...] = ("yahoo", "espn")


class ConnectionStatus(BaseModel):
    platform: Platform
    is_connected: bool
    display_name: str | None = None
    last_verified_at: datetime | None = None


class YahooStartResponse(BaseModel):
    auth_url: str


class EspnTestRequest(BaseModel):
    swid: str
    espn_s2: str

    @field_validator("swid")
    @classmethod
    def validate_swid(cls, value: str) -> str:
        if not SWID_PATTERN.match(value):
            raise ValueError(r"swid must match ^\{[0-9A-Fa-f-]+\}$")
        return value


def _to_status(row: Connection | None, platform: Platform) -> ConnectionStatus:
    if row is None:
        return ConnectionStatus(platform=platform, is_connected=False)
    if platform == "yahoo":
        is_connected = row.access_token_enc is not None
    else:
        is_connected = row.swid_enc is not None and row.espn_s2_enc is not None
    return ConnectionStatus(
        platform=platform,
        is_connected=is_connected,
        display_name=row.display_name,
        last_verified_at=row.last_verified_at,
    )


@router.get("", response_model=list[ConnectionStatus])
async def list_connections(session: AsyncSession = Depends(get_session)) -> list[ConnectionStatus]:
    statuses = []
    for platform in PLATFORMS:
        row = await session.get(Connection, platform)
        statuses.append(_to_status(row, platform))
    return statuses


@router.post("/yahoo/start", response_model=YahooStartResponse)
async def yahoo_start(settings: Settings = Depends(get_settings)) -> YahooStartResponse:
    auth_url, _state = oauth.build_authorization_url(settings)
    return YahooStartResponse(auth_url=auth_url)


@router.get("/yahoo/callback")
async def yahoo_callback(
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not oauth.verify_state(state, settings.gridiron_secret_key):
        raise HTTPException(
            status_code=400, detail={"code": "invalid_state", "message": "state invalid or expired"}
        )

    try:
        tokens = await oauth.exchange_code(settings, code)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "token_exchange_failed", "message": str(exc)},
        ) from exc

    access_token_enc = credentials.encrypt(settings.gridiron_secret_key, tokens["access_token"])
    refresh_token_enc = credentials.encrypt(settings.gridiron_secret_key, tokens["refresh_token"])

    row = await session.get(Connection, "yahoo")
    now = datetime.now(UTC)
    if row is None:
        row = Connection(platform="yahoo")
        session.add(row)
    row.access_token_enc = access_token_enc
    row.refresh_token_enc = refresh_token_enc
    row.last_verified_at = now
    await session.commit()

    return RedirectResponse(url=settings.gridiron_base_url.rstrip("/") + "/settings")


@router.post("/espn/test", response_model=ConnectionStatus)
async def espn_test(
    body: EspnTestRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ConnectionStatus:
    client = EspnClient(settings, swid=body.swid, espn_s2=body.espn_s2)
    try:
        try:
            year = datetime.now(UTC).year
            league_ids = await client.discover_leagues(year)
            # `discover_leagues` doesn't actually check `espn_s2` (ESPN accepts any/no
            # value there) — only a real per-league fetch enforces it, so that's what
            # decides accept/reject. No leagues found yet is treated as accepted; the
            # cookies will be validated for real the first time a league is added.
            if league_ids:
                await client.probe_league(league_ids[0], year)
        except (AuthRequiredError, httpx.HTTPStatusError) as exc:
            # AuthRequiredError is the expected bad-cookie case (401/403 from the
            # per-league probe). A non-auth HTTPStatusError here almost always means
            # `SWID` doesn't match any real ESPN account (the fan API 404s rather
            # than 401ing for those) — surfacing both as one rejection keeps this
            # endpoint from 500ing on malformed-but-regex-valid input.
            raise HTTPException(
                status_code=422,
                detail={"code": "auth_required", "message": "ESPN rejected the provided cookies"},
            ) from exc
    finally:
        await client.aclose()

    swid_enc = credentials.encrypt(settings.gridiron_secret_key, body.swid)
    espn_s2_enc = credentials.encrypt(settings.gridiron_secret_key, body.espn_s2)

    row = await session.get(Connection, "espn")
    now = datetime.now(UTC)
    if row is None:
        row = Connection(platform="espn")
        session.add(row)
    row.swid_enc = swid_enc
    row.espn_s2_enc = espn_s2_enc
    row.last_verified_at = now
    await session.commit()
    await session.refresh(row)

    return _to_status(row, "espn")


@router.delete("/{platform}", status_code=204)
async def delete_connection(
    platform: Platform, session: AsyncSession = Depends(get_session)
) -> None:
    await session.execute(delete(Connection).where(Connection.platform == platform))
    await session.commit()
