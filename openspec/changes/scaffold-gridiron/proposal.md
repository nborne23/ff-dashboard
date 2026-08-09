## Why

Yahoo and ESPN each force the user into a separate web app with its own scoring, layout, and refresh cadence. With teams across both platforms, comparing standings on game day means juggling tabs, neither of which surfaces what actually matters mid-game (point swings, live red-zone players, projected finals). GridIron consolidates every team into one Apple Health–styled dashboard with shared scoring and a single design language so the user can see all leagues in one glance.

The deployment target is **self-hosted on the user's 2019 Intel iMac**: a single always-on FastAPI process (managed by launchd) that serves the API, an SSE event stream, and the built frontend, reachable from the user's phone and laptop over **Tailscale** (with Tailscale Serve providing a stable HTTPS URL). An always-on process removes every serverless constraint the previous Vercel plan designed around: the in-process scheduler replaces cron jobs, SQLite replaces a hosted Postgres, a disk folder replaces blob storage, and **true real-time push via SSE is back in scope** — the frontend receives updates the moment the backend's cache refreshes, instead of polling on a timer. Hosting cost is $0/month (the iMac's electricity aside).

## What Changes

This is a greenfield project — every change is additive.

- **Backend (Python 3.12 + FastAPI, one long-running uvicorn process)**
  - Single FastAPI app serving `/api/*` routes, the `/api/events` SSE stream, and the static frontend build (`frontend/dist`) — one process, one port.
  - Yahoo Fantasy OAuth 2.0 client: authorization-code flow, token refresh, JSON-format responses, dynamic NFL `game_key` resolution, league/team/roster/matchup fetching.
  - ESPN Fantasy client: cookie-based auth (`SWID` + `espn_s2`), `view`-stacked queries, base-URL configurable via env var.
  - Unified `FantasyService` that maps both platforms onto a normalized internal model.
  - **SQLite** (SQLAlchemy async + `aiosqlite`, WAL mode) holds normalized entities, encrypted credentials, and an `http_cache` table. One file at `data/gridiron.db`, trivially backed up.
  - **APScheduler (in-process)** drives cache refresh: an adaptive refresh loop runs at 30 s during live games, 5 min on game days, 30 min on off-days, plus a daily discovery/credential-probe job. No external cron, no cron auth secret.
  - **SSE push**: when a scheduler tick writes fresh data to the cache, the backend diffs it against the prior snapshot and publishes events on an in-process asyncio bus; `/api/events` streams them to connected clients.
  - Live NFL game-state classifier backed by ESPN's free public scoreboard, refreshed by the scheduler.
  - **Local headshot cache**: player headshots are fetched once, stored under `data/headshots/`, and served by FastAPI with long-lived cache headers.
- **Frontend (React 18 + TypeScript + Vite, served as static files by the backend)**
  - Five screens — Dashboard, My Team, Head-to-Head, Season, Settings — that pixel-perfectly reproduce `GridIron.html` from the Claude Design project (<https://claude.ai/design/p/1692dcc6-8418-4f8f-9139-5d19358beaca?file=GridIron.html>), imported via the claude_design MCP (`https://api.anthropic.com/v1/design/mcp`, auth via `/design-login`) at the start of Phase 1.
  - Design tokens lifted directly from `styles.css` (CSS custom properties), no Tailwind.
  - SVG charts (ActivityRing, Sparkline, BarChart, HorizBar, SeasonChart) rewritten as proper React components — no Recharts/D3 dependency.
  - **SSE-driven live-feel**: an `EventSource` connection to `/api/events` invalidates the matching TanStack Query keys the moment the backend has fresh data — updates appear within ~1 s of the cache write. A slow `refetchInterval` (5 min) remains as a fallback when the SSE connection is down, with automatic reconnect + backoff.
  - A small "changed value" pulse animation (600 ms opacity flash) fires when an updated value differs from the previously-rendered value.
  - React Router v6 for the five top-level screens; Zustand for transient UI state (sidebar collapse, week selector, tweaks panel).
- **Operations**
  - Python environment pinned with **uv** (`.python-version` + `uv.lock`) so the M4 dev machine and the Intel iMac run identical environments despite different CPU architectures. No Docker.
  - **launchd LaunchAgent** keeps the process running on the iMac: starts on boot, restarts on crash, logs to `~/Library/Logs/gridiron/`.
  - **Tailscale Serve** exposes the app inside the tailnet as `https://<imac>.<tailnet>.ts.net` with a valid certificate (required for the Yahoo OAuth redirect URI).
  - `make deploy` from the dev machine: SSH to the iMac over Tailscale, `git pull`, `uv sync`, `npm run build`, `alembic upgrade head`, restart the LaunchAgent.
  - iMac power configuration: `pmset` prevents system sleep (display sleep is fine), auto-restart after power failure, wake for network access.
  - `.env` on the iMac carries Yahoo client ID/secret and `GRIDIRON_SECRET_KEY`; no other service tokens exist.

## Capabilities

### New Capabilities

- `platform-integrations`: OAuth/cookie auth, league/team/roster/matchup fetching, retry + backoff, error taxonomy for both Yahoo and ESPN, local-disk headshot cache.
- `fantasy-data-model`: Normalized internal entities (`Platform`, `League`, `Team`, `Player`, `RosterSlot`, `Matchup`, `MatchupSlot`, `SeasonWeek`), per-platform mappers, SQLite persistence with cache TTLs.
- `live-updates`: NFL game-state detection, in-process adaptive refresh scheduler, SSE push protocol with polling fallback, freshness/last-updated semantics.
- `gridiron-ui`: Five-screen React shell with the Apple Health design language, week selector, design tokens, responsive breakpoints, and SSE-driven live updates.

### Modified Capabilities

None — there are no existing specs.

## Impact

- **Repo layout**: `backend/` (FastAPI app + scheduler), `frontend/` (Vite-built static SPA), `deploy/` (launchd plist, setup script), `data/` (SQLite file + headshots, gitignored), `.env.example`, `Makefile` for dev/deploy shortcuts.
- **External dependencies**:
  - Backend: `fastapi`, `uvicorn`, `httpx`, `sqlalchemy` (async), `aiosqlite`, `alembic`, `apscheduler`, `sse-starlette`, `cryptography` (cookie encryption), `pydantic`, `pydantic-settings`, `authlib` (OAuth), `pytest`, `pytest-asyncio`, `respx`. Managed with `uv`.
  - Frontend: `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `zustand`, `vite`, `typescript`, `vitest`, `@testing-library/react`.
- **Third-party services**:
  - Tailscale free Personal plan (6 users, unlimited devices) — remote access + HTTPS via Tailscale Serve. Nothing is exposed to the public internet.
  - Yahoo Developer app (Client ID/Secret).
  - ESPN cookies extracted manually by user (no developer registration). ESPN's unofficial API may break — wrap defensively.
  - No hosted database, no blob store, no cron service, no CDN.
- **Secrets at rest**: ESPN `espn_s2` and Yahoo refresh tokens encrypted with Fernet using `GRIDIRON_SECRET_KEY` env var, stored in the SQLite `connections` table.
- **iMac-hosting gotchas**:
  - The machine must be awake during games: `pmset -c sleep 0`, auto-restart after power failure, and auto-login + LaunchAgent cover the common failure modes.
  - The 2019 iMac tops out at macOS Sequoia (Tahoe dropped it); security updates run through ~2027. Acceptable risk while nothing is publicly exposed; the long-term escape hatch is Linux on the same hardware or any $5/mo VPS — the architecture (one process + SQLite) ports unchanged.
  - ~24–35 W idle power draw (≈ $3–5/month electricity if run year-round); the app can simply be shut down in the off-season.
  - SQLite is single-writer: all writes flow through the one backend process, which is exactly our topology. WAL mode keeps reads non-blocking.

## Decisions made for this scaffold

These were called out in the brief as open questions, plus the ones settled by the iMac hosting decision. Defaults so the design/tasks artifacts can be concrete; flag any to override before /opsx:apply.

| Question | Default | Rationale |
| --- | --- | --- |
| Hosting | **Self-hosted on the user's 2019 iMac** | User-stated requirement. One always-on FastAPI process behind Tailscale. $0/mo; no serverless constraints. |
| Backend language | **Python (FastAPI on uvicorn)** | The two reference libraries (`yfpy`, `cwendt94/espn-api`) are Python and have already solved Yahoo XML→JSON quirks and ESPN view-stacking. |
| Database | **SQLite (aiosqlite + WAL)** | One user, one process, one disk. Zero services to manage; backup is copying a file. SQLAlchemy + Alembic keep a future Postgres move cheap. |
| Live updates | **SSE push from the in-process scheduler** | The always-on process makes the originally-planned SSE design viable. Frontend gets sub-second update latency; a slow polling fallback covers SSE disconnects. |
| Background polling | **APScheduler in-process, adaptive cadence (30 s live / 5 min game day / 30 min off-day)** | No cron infrastructure at all; the scheduler and the web app share memory, which is what enables SSE publishing. |
| File / asset storage | **Local disk (`data/headshots/`)** | The iMac has a disk. FastAPI serves the files with long-lived cache headers. |
| Remote access | **Tailscale-only via Tailscale Serve** | Free, private, valid HTTPS for the OAuth redirect, and no auth layer needed — nothing is publicly reachable. |
| Env reproducibility | **uv (`.python-version` + `uv.lock`), no Docker** | Dev machine is arm64, iMac is x86_64 — Docker images don't port; uv lockfiles do. Docker Desktop's VM overhead is unwelcome on an always-on 2019 iMac. |
| Repo shape | **Single root with `backend/` + `frontend/` + `deploy/`** | One process serves both; one repo deploys with one `git pull`. |
| Mobile native | **No — desktop-first, responsive only** | Design bundle has 1024/768 breakpoints but no native mockups. Stay within those (they're what the phone will use over Tailscale). |
| "Best Possible Lineup" feature | **Out of scope for v1** | Optimization/recommendation feature is orthogonal to the read-only consumption story; defer until live updates and full data model are stable. |
| Auth scope | **Single user; network-level auth via tailnet membership** | Only devices in the user's tailnet can reach the app. No login screen, no sessions. |
| Charting library | **Hand-rolled SVG** | Prototype already gave us full implementations; pulling in Recharts/D3 adds bytes without solving anything. |
| State management | **TanStack Query (server) + Zustand (UI)** | Query's cache is the render source; SSE events invalidate keys instead of timers. Zustand for sidebar/week/tweaks panel. |

## Out of scope (call out for later)

- Mock-data drafting / lineup recommendations / trade analyzers.
- Multi-user accounts, sharing, or commissioner tools. (Sharing with league-mates would require the public-URL + auth architecture — Cloudflare Tunnel + Access — documented but not built.)
- Push notifications (the design's notification toggles are visible-but-non-functional in v1).
- Light theme / accent picker actually rewiring colors (UI exists, swap is v2).
- Historical season data beyond what Yahoo/ESPN return for the current season.
- Public internet exposure. v1 is tailnet-only; the escape hatch (Cloudflare Tunnel + Access, or a VPS move) is documented in the README.
