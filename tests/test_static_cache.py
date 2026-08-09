"""Task 11.6: cache headers for the built frontend — hashed `dist/assets/*` files get a
year-long immutable cache, `index.html` (the SPA entry point, always served at unhashed
URLs) never gets cached at all."""

import httpx
import pytest

from backend.main import FRONTEND_DIST, ASSETS_CACHE_CONTROL, INDEX_CACHE_CONTROL, app

pytestmark = pytest.mark.skipif(
    not (FRONTEND_DIST / "assets").is_dir(),
    reason="no frontend build present (run `npm run build`)",
)


def _an_asset_filename() -> str:
    return next((FRONTEND_DIST / "assets").iterdir()).name


@pytest.mark.asyncio
async def test_hashed_asset_gets_immutable_year_long_cache() -> None:
    filename = _an_asset_filename()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/assets/{filename}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == ASSETS_CACHE_CONTROL


@pytest.mark.asyncio
async def test_index_html_is_never_cached() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == INDEX_CACHE_CONTROL


@pytest.mark.asyncio
async def test_spa_fallback_route_also_gets_no_cache_index_html() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/team/yahoo:1")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == INDEX_CACHE_CONTROL


@pytest.mark.asyncio
async def test_api_path_under_the_fallback_route_still_404s() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
