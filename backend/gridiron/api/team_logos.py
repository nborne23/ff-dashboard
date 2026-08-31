"""`GET /api/team-logos/{platform}/{team_id}` — disk-cached team logo serving.

Deliberately extensionless, unlike `/api/headshots/{...}.png`: the cached bytes may be
SVG or JPEG and the format is a property of the stored row, not of the path.

This route is not a convenience. ESPN's uploaded-logo host returns 401 to an
unauthenticated client, so the browser cannot fetch those images itself — proxying
them through here, with the stored session cookies, is the only way they render.
"""

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session
from backend.gridiron.services import team_logos

router = APIRouter(prefix="/api/team-logos", tags=["team-logos"])

# Shorter than the headshot cache's `immutable` day: a leaguemate can change their logo
# at any time, and the source-URL comparison that detects it only runs when the browser
# actually asks us again.
CACHE_CONTROL = "public, max-age=3600"

# The bytes are served with a stored content type, and one of the allowed types is SVG.
# `nosniff` stops a browser re-interpreting a mislabeled raster payload as markup.
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff"}


@router.get("/{platform}/{team_id}")
async def get_team_logo(
    platform: str = Path(..., pattern=team_logos.PLATFORM_PATTERN.pattern),
    team_id: str = Path(..., pattern=team_logos.TEAM_ID_PATTERN.pattern),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    headers = {"Cache-Control": CACHE_CONTROL, **SECURITY_HEADERS}

    cached = await team_logos.cached_entry(settings, session, platform, team_id)
    if cached is not None:
        content, content_type = cached
        return Response(content=content, media_type=content_type, headers=headers)

    content, content_type = await team_logos.fetch_and_cache(settings, session, platform, team_id)
    return Response(content=content, media_type=content_type, headers=headers)
