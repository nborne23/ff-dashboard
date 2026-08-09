"""Disk-cached player headshot fetch/store (design.md D10).

Layout: `data/headshots/{platform}/{player_id}.png`. The API layer (`api/headshots.py`)
owns the disk-hit fast path (serve straight from disk, no DB/network); this module owns
what happens on a miss: fetch upstream, write to disk, or fall back to the bundled
silhouette on a 404 (a permanent negative cache — the file written IS the fallback, so
the next request is a disk-hit like any other).
"""

import re
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import Settings
from backend.gridiron.models import Headshot

REPO_ROOT = Path(__file__).resolve().parents[3]

# Path-traversal guard: allowlist regexes for both path params (design.md D10 + task 3.11).
PLATFORM_PATTERN = re.compile(r"^(yahoo|espn)$")
PLAYER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

ESPN_HEADSHOT_URL = "https://a.espncdn.com/i/headshots/nfl/players/full/{player_id}.png"

SILHOUETTE_PATH = Path(__file__).resolve().parent.parent / "assets" / "silhouette.png"


def resolve_headshots_dir(settings: Settings) -> Path:
    """Resolve `settings.gridiron_headshots_path` to an absolute path."""
    path = Path(settings.gridiron_headshots_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def headshot_path(settings: Settings, platform: str, player_id: str) -> Path:
    return resolve_headshots_dir(settings) / platform / f"{player_id}.png"


def is_valid_platform(platform: str) -> bool:
    return bool(PLATFORM_PATTERN.match(platform))


def is_valid_player_id(player_id: str) -> bool:
    return bool(PLAYER_ID_PATTERN.match(player_id))


def read_silhouette() -> bytes:
    return SILHOUETTE_PATH.read_bytes()


def _write_silhouette(dest: Path) -> bytes:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = read_silhouette()
    dest.write_bytes(data)
    return data


async def fetch_and_cache(
    settings: Settings,
    session: AsyncSession,
    platform: str,
    player_id: str,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Resolve a headshot that isn't on disk yet: fetch upstream, cache it, and return bytes.

    ESPN has a deterministic CDN URL. Yahoo has none, so its source URL must already be
    known from a `Headshot` row (populated during discovery/roster sync); if that row is
    missing, this falls straight to the silhouette without a network call.

    On an upstream 404 the silhouette is written to `dest` (negative cache: the next
    request becomes a disk-hit). On any other failure the silhouette is served but NOT
    persisted, so a later request retries the upstream fetch.
    """
    dest = headshot_path(settings, platform, player_id)

    if platform == "espn":
        source_url: str | None = ESPN_HEADSHOT_URL.format(player_id=player_id)
    else:
        row = await session.get(Headshot, (platform, player_id))
        source_url = row.source_url if row is not None else None

    if source_url is None:
        return _write_silhouette(dest)

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=15)
    try:
        try:
            response = await client.get(source_url)
        except httpx.HTTPError:
            return read_silhouette()
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 404:
        return _write_silhouette(dest)
    if response.is_error:
        return read_silhouette()

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return response.content
