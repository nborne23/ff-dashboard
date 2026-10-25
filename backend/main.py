"""FastAPI application factory for GridIron."""

import ipaddress
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from backend.gridiron import scheduler
from backend.gridiron.api.admin import router as admin_router
from backend.gridiron.api.connections import router as connections_router
from backend.gridiron.api.data import router as data_router
from backend.gridiron.api.draft import router as draft_router
from backend.gridiron.api.events import router as events_router
from backend.gridiron.api.headshots import router as headshots_router
from backend.gridiron.api.players import router as players_router
from backend.gridiron.api.team_logos import router as team_logos_router
from backend.gridiron.api.leagues import router as leagues_router
from backend.gridiron.api.settings import router as settings_router
from backend.gridiron.api.teams import router as teams_router
from backend.gridiron.config import get_settings
from backend.gridiron.logging_config import configure_logging

# Reuse uvicorn's own logger so this shows up on boot without extra logging
# config (the app is only ever run under uvicorn, per the launchd plist).
logger = logging.getLogger("uvicorn.error")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Task 11.6: cache headers for the built frontend. Vite hashes every filename under
# `dist/assets` (e.g. `index-a1b2c3d4.js`), so a given URL only ever names one immutable
# byte sequence — a new build is a new URL, never a mutated old one — hence the
# aggressive year-long `immutable` cache. `index.html` is the one unhashed entry point
# (always served at `/`), so it must never be cached: it's the thing that references the
# current build's hashed asset URLs, and a stale cached copy would keep pointing at a
# deleted previous build's assets after a deploy.
ASSETS_CACHE_CONTROL = "public, max-age=31536000, immutable"
INDEX_CACHE_CONTROL = "no-cache"


class ImmutableStaticFiles(StaticFiles):
    """`StaticFiles` that stamps every response with `ASSETS_CACHE_CONTROL`."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = ASSETS_CACHE_CONTROL
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.gridiron_scheduler_enabled:
        scheduler.start_scheduler()
    else:
        # Dev default (design.md D13.3): no scheduler; POST /api/admin/refresh still works.
        logger.info("scheduler disabled (GRIDIRON_SCHEDULER_ENABLED=false)")
    try:
        yield
    finally:
        scheduler.shutdown_scheduler()


# This app has unauthenticated /api/admin and /api/connections routes, so it must only ever
# answer devices on the tailnet. It can no longer rely on the bind address to enforce that:
# uvicorn takes a single --host, `tailscale serve` can only proxy to loopback, and a phone
# whose DNS bypasses MagicDNS needs the tailnet address directly — so it binds 0.0.0.0 and
# the check moves here.
_ALLOWED_CLIENT_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("100.64.0.0/10"),  # Tailscale IPv4 (CGNAT range)
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),  # Tailscale IPv6
)


def client_is_allowed(host: str | None) -> bool:
    """True for loopback and tailnet addresses, false for the LAN and everything else."""
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return any(addr in net for net in _ALLOWED_CLIENT_NETS)


def create_app() -> FastAPI:
    configure_logging(get_settings().gridiron_log_dir)
    app = FastAPI(title="GridIron", lifespan=lifespan)

    @app.middleware("http")
    async def restrict_to_tailnet(request: Request, call_next):
        if not client_is_allowed(request.client.host if request.client else None):
            return PlainTextResponse("Not available on this network.", status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(connections_router)
    app.include_router(headshots_router)
    app.include_router(team_logos_router)
    app.include_router(leagues_router)
    app.include_router(settings_router)
    app.include_router(teams_router)
    app.include_router(players_router)
    app.include_router(admin_router)
    app.include_router(data_router)
    app.include_router(draft_router)
    app.include_router(events_router)

    if FRONTEND_DIST.is_dir():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", ImmutableStaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api"):
                raise HTTPException(status_code=404)
            return FileResponse(
                FRONTEND_DIST / "index.html", headers={"Cache-Control": INDEX_CACHE_CONTROL}
            )

    return app


app = create_app()
