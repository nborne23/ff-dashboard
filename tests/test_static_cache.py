"""Task 11.6: cache headers for the built frontend — hashed `dist/assets/*` files get a
year-long immutable cache, `index.html` (the SPA entry point, always served at unhashed
URLs) never gets cached at all."""

import httpx
import pytest

from backend.main import FRONTEND_DIST, ASSETS_CACHE_CONTROL, INDEX_CACHE_CONTROL, app

_needs_build = pytest.mark.skipif(
    not (FRONTEND_DIST / "assets").is_dir(),
    reason="no frontend build present (run `npm run build`)",
)


def _an_asset_filename() -> str:
    return next((FRONTEND_DIST / "assets").iterdir()).name


@_needs_build
@pytest.mark.asyncio
async def test_hashed_asset_gets_immutable_year_long_cache() -> None:
    filename = _an_asset_filename()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/assets/{filename}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == ASSETS_CACHE_CONTROL


@_needs_build
@pytest.mark.asyncio
async def test_index_html_is_never_cached() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == INDEX_CACHE_CONTROL


@_needs_build
@pytest.mark.asyncio
async def test_spa_fallback_route_also_gets_no_cache_index_html() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/team/yahoo:1")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == INDEX_CACHE_CONTROL


@_needs_build
@pytest.mark.asyncio
async def test_api_path_under_the_fallback_route_still_404s() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/does-not-exist")

    assert response.status_code == 404


# `resolve_root_file` runs against a throwaway dist, so these don't need a real build.
class TestResolveRootFile:
    @pytest.fixture
    def dist(self, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html>")
        (dist / "sw.js").write_text("self.addEventListener('push', () => {});")
        (dist / "manifest.webmanifest").write_text("{}")
        (tmp_path / ".env").write_text("SECRET=1")
        return dist

    def test_serves_a_top_level_file(self, dist) -> None:
        from backend.main import resolve_root_file

        assert resolve_root_file(dist, "sw.js") == (dist / "sw.js").resolve()
        assert resolve_root_file(dist, "manifest.webmanifest") is not None

    def test_spa_routes_and_unknown_files_fall_through(self, dist) -> None:
        from backend.main import resolve_root_file

        assert resolve_root_file(dist, "") is None
        assert resolve_root_file(dist, "team/yahoo:1") is None
        assert resolve_root_file(dist, "settings") is None
        assert resolve_root_file(dist, "index.html") is None

    def test_refuses_to_leave_dist(self, dist) -> None:
        from backend.main import resolve_root_file

        assert resolve_root_file(dist, "../.env") is None
        assert resolve_root_file(dist, "..") is None

    def test_media_types_cover_the_push_files(self) -> None:
        from backend.main import ROOT_FILE_MEDIA_TYPES

        assert ROOT_FILE_MEDIA_TYPES[".webmanifest"] == "application/manifest+json"
        assert ROOT_FILE_MEDIA_TYPES[".js"] == "text/javascript"
