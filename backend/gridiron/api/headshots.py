"""`GET /api/headshots/{platform}/{player_id}.png` — disk-cached headshot serving (design.md D10)."""

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session
from backend.gridiron.services import headshots

router = APIRouter(prefix="/api/headshots", tags=["headshots"])

CACHE_CONTROL = "public, max-age=86400, immutable"


@router.get("/{platform}/{player_id}.png")
async def get_headshot(
    platform: str = Path(..., pattern=headshots.PLATFORM_PATTERN.pattern),
    player_id: str = Path(..., pattern=headshots.PLAYER_ID_PATTERN.pattern),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    dest = headshots.headshot_path(settings, platform, player_id)

    if dest.is_file():
        return FileResponse(dest, media_type="image/png", headers={"Cache-Control": CACHE_CONTROL})

    content = await headshots.fetch_and_cache(settings, session, platform, player_id)
    return Response(
        content=content, media_type="image/png", headers={"Cache-Control": CACHE_CONTROL}
    )
