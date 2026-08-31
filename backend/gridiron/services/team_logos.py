"""Disk-cached fantasy-team logo fetch/store.

A sibling of `headshots.py`, not an extension of it (add-league-standings design D1).
Three things differ, and each one breaks a headshot assumption:

- **Format.** Headshots are always PNG, so the module bakes it into the route suffix,
  the filename, and the fallback. Logos arrive as `image/svg+xml` (ESPN's stock set)
  and `image/jpg` (uploads, from an extensionless URL), so the format has to be stored
  per row and the cached file carries no extension.
- **Auth.** Headshots come from a public CDN. An uploaded team logo returns **401
  without ESPN session cookies**, which is why the bytes are proxied at all — a
  browser pointed at the upstream URL gets an error, not an image.
- **Invalidation.** Headshot URLs are stable. An uploaded logo's URL carries a
  generated id that changes when the image changes, so the stored source URL is
  compared and a mismatch forces a refetch (D5).
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings
from backend.gridiron.models import Connection, Team, TeamLogo
from backend.gridiron.services import credentials

REPO_ROOT = Path(__file__).resolve().parents[3]

# Path-traversal guards. Team ids carry dots on Yahoo (`nfl.l.123456.t.4`) and dashes
# on ESPN (`l-652756302-t-2`), but never a slash or `..`.
PLATFORM_PATTERN = re.compile(r"^(yahoo|espn)$")
TEAM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

CREST_PATH = Path(__file__).resolve().parent.parent / "assets" / "crest.svg"
CREST_CONTENT_TYPE = "image/svg+xml"

# Raster types an uploaded logo may use. `image/jpg` is nonstandard but is what ESPN
# actually reports for JPEG data, so it is listed explicitly rather than normalized.
ALLOWED_RASTER_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
)

# SVG is accepted ONLY from this host (design D6). An SVG served from our own origin
# can carry <script> with same-origin access to everything the app can reach; ESPN's
# stock logos live here, while uploaded logos are other league members' content.
SVG_ALLOWED_HOSTS = frozenset({"g.espncdn.com"})


def resolve_logos_dir(settings: Settings) -> Path:
    path = Path(settings.gridiron_team_logos_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def logo_path(settings: Settings, platform: str, team_id: str) -> Path:
    """No extension: the cached bytes may be vector or raster, and the database row is
    the authority on which."""
    return resolve_logos_dir(settings) / platform / team_id


def is_valid_platform(platform: str) -> bool:
    return bool(PLATFORM_PATTERN.match(platform))


def is_valid_team_id(team_id: str) -> bool:
    return bool(TEAM_ID_PATTERN.match(team_id))


def read_crest() -> bytes:
    return CREST_PATH.read_bytes()


def content_type_is_allowed(content_type: str | None, source_url: str) -> bool:
    """Design D6's allowlist.

    SVG passes only from the platform's own stock-logo host. Everything else must be a
    raster type. Anything unrecognized is rejected, so a payload that is not an image
    at all never reaches the browser wearing an image content type.
    """
    if not content_type:
        return False
    base = content_type.split(";")[0].strip().lower()
    if base == "image/svg+xml":
        return urlparse(source_url).hostname in SVG_ALLOWED_HOSTS
    return base in ALLOWED_RASTER_TYPES


async def _espn_cookie_header(settings: Settings, session: AsyncSession) -> dict[str, str]:
    """ESPN session cookies, or `{}` when ESPN is not connected.

    Returning empty rather than raising is deliberate (design D3): a fresh install with
    no credentials should render crests, not raise once per team on the dashboard.
    """
    conn = await session.get(Connection, "espn")
    if conn is None or not conn.swid_enc or not conn.espn_s2_enc:
        return {}
    swid = credentials.decrypt(settings.gridiron_secret_key, conn.swid_enc)
    espn_s2 = credentials.decrypt(settings.gridiron_secret_key, conn.espn_s2_enc)
    return {"Cookie": f"SWID={swid}; espn_s2={espn_s2}"}


async def cached_entry(
    settings: Settings, session: AsyncSession, platform: str, team_id: str
) -> tuple[bytes, str] | None:
    """Cached bytes + content type, or `None` when the cache is absent or stale.

    Stale means the team's current `logo_source_url` differs from the one these bytes
    were fetched for — how a changed logo is detected without a TTL (design D5).
    """
    dest = logo_path(settings, platform, team_id)
    if not dest.is_file():
        return None

    row = await session.get(TeamLogo, (platform, team_id))
    if row is None or not row.content_type:
        return None

    team = await session.get(Team, f"{platform}:{team_id}")
    current_source = team.logo_source_url if team is not None else None
    if current_source != row.source_url:
        return None

    return dest.read_bytes(), row.content_type


async def fetch_and_cache(
    settings: Settings,
    session: AsyncSession,
    platform: str,
    team_id: str,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    """Fetch a team's logo, cache it, and return `(bytes, content_type)`.

    Falls back to the crest — without caching the failure — whenever the logo cannot be
    used: no source URL, a transport error, a 401, or a content type the allowlist
    rejects. A 401 in particular must stay retryable (design D4): expired ESPN cookies
    are a recoverable state this app already has a reconnect flow for, and caching that
    failure would blank every team's logo until the cache was cleared by hand.
    """
    team = await session.get(Team, f"{platform}:{team_id}")
    source_url = team.logo_source_url if team is not None else None
    if not source_url:
        return read_crest(), CREST_CONTENT_TYPE

    headers = await _espn_cookie_header(settings, session) if platform == "espn" else {}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=15, follow_redirects=True)
    try:
        try:
            response = await client.get(source_url, headers=headers)
        except httpx.HTTPError:
            return read_crest(), CREST_CONTENT_TYPE
    finally:
        if owns_client:
            await client.aclose()

    if response.is_error:
        # 404 could be recorded as a permanent absence, but a 401 must not be, and
        # distinguishing them buys little here: the next request simply retries, which
        # is the correct behavior for the recoverable case and harmless for the other.
        return read_crest(), CREST_CONTENT_TYPE

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type_is_allowed(content_type, source_url):
        return read_crest(), CREST_CONTENT_TYPE

    dest = logo_path(settings, platform, team_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)

    row = await session.get(TeamLogo, (platform, team_id))
    if row is None:
        row = TeamLogo(platform=platform, team_id=team_id)
        session.add(row)
    row.source_url = source_url
    row.content_type = content_type
    row.fetched_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()

    return response.content, content_type
