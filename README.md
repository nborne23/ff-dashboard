# GridIron

Single-user fantasy football dashboard aggregating Yahoo + ESPN leagues into one
Apple Health–styled view with live SSE updates. Self-hosted on a Mac (target: a
2019 iMac) as one always-on FastAPI process under launchd, reachable from phone
and laptop over Tailscale.

## Stack

- **Backend**: Python 3.12, FastAPI + uvicorn, SQLite (SQLAlchemy async + aiosqlite),
  APScheduler in-process, SSE via sse-starlette. Env managed with [uv](https://docs.astral.sh/uv/).
- **Frontend**: React 18 + TypeScript + Vite, TanStack Query, Zustand, hand-rolled SVG charts.
  Built to `frontend/dist` and served as static files by the backend.
- **Design source**: `GridIron.html` in the Claude Design project (vendored under `design/`).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — backend package/venv manager (`brew install uv`, or the
  standalone installer: `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- **Node 18+** — frontend build (`brew install node`, or the `.pkg` installer from
  <https://nodejs.org/en/download> on machines where Homebrew isn't available, e.g. older
  macOS versions).
- **git** — ships via Xcode Command Line Tools (`xcode-select --install`); no Homebrew needed.
- **Tailscale** — installed and signed into the *same* tailnet on every device that
  needs access: the iMac (serves the app), your dev machine, and your phone. The iMac
  additionally runs `tailscale serve` (done by `deploy/setup-imac.sh`), which gives it a
  stable `https://<imac>.<tailnet>.ts.net` address with a Tailscale-managed TLS cert —
  no port-forwarding or public DNS involved. Run `tailscale serve --bg 8000` on your dev
  machine too (same command, manually) — Yahoo's OAuth console now rejects plain
  `http://` redirect URIs outright, so dev needs its own https tailnet address just like
  prod.
- **A Yahoo developer app** — create one at <https://developer.yahoo.com/apps/> with
  read access to the Fantasy Sports API, then register **both** redirect URIs on it as
  https tailnet URLs (Yahoo requires an exact match and https; dev and prod are separate
  registrations):
  - dev: `https://<dev-machine>.<tailnet>.ts.net/api/connections/yahoo/callback`
  - prod: `https://<imac>.<tailnet>.ts.net/api/connections/yahoo/callback`

  Put the app's client id/secret in `.env` (below). ESPN needs no app registration — it
  authenticates via the `SWID`/`espn_s2` cookies from a logged-in browser session
  (entered in Settings → ESPN Credentials).

## One-time iMac setup

From a fresh macOS user account on the iMac:

```sh
git clone <this repo> ~/gridiron
cd ~/gridiron
./deploy/setup-imac.sh
```

`deploy/setup-imac.sh` is idempotent (safe to re-run) and handles: installing
uv/node via Homebrew, `uv sync` + frontend build, prompting you to fill in `.env`,
running Alembic migrations, `pmset` power settings (sleep disabled, wake-on-network —
a couple of steps still need the System Settings GUI; the script prints exactly
which), `tailscale serve --bg 8000`, and installing + bootstrapping the
`com.gridiron.app` LaunchAgent (`deploy/com.gridiron.app.plist`), finishing with a
health check.

After that one-time setup, ship new code from your dev machine with:

```sh
make deploy IMAC_HOST=<tailnet-hostname>
```

which runs `deploy/deploy.sh` on the iMac over ssh: `git pull --ff-only`, `uv sync`,
rebuild the frontend, `alembic upgrade head`, `launchctl kickstart` the LaunchAgent,
then polls `/api/health` until it's back up (or fails loudly with the log paths).

## .env setup

```sh
cp .env.example .env
```

Then fill in:

| Variable | Notes |
|---|---|
| `GRIDIRON_SECRET_KEY` | Generate once: `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Encrypts Yahoo tokens + ESPN cookies at rest. **Losing this key means re-entering ESPN cookies and redoing Yahoo OAuth** — back up `.env` accordingly (Time Machine covers this on the iMac). |
| `YAHOO_CLIENT_ID` / `YAHOO_CLIENT_SECRET` | From the Yahoo developer app above. |
| `GRIDIRON_BASE_URL` | `https://<dev-machine>.<tailnet>.ts.net` in dev, `https://<imac>.<tailnet>.ts.net` in prod — used to build the Yahoo OAuth redirect, so it must match whichever URL you're actually reaching the app through (must be https; Yahoo rejects `http://localhost` redirect URIs). |
| `ESPN_BASE_URL` | Only override if ESPN moves their API host. |
| `GRIDIRON_SCHEDULER_ENABLED` | `false` in dev (default) — see "Dev workflow" below. `true` in prod. |
| `GRIDIRON_DB_PATH` | SQLite file location, created on boot. |
| `GRIDIRON_LOG_DIR` | Empty (default) = console-only. Set to a directory for rotated log files too — the iMac's LaunchAgent sets this to `~/Library/Logs/gridiron` (see "Logs" below). |

## Dev workflow

```sh
uv sync                        # backend deps (pinned by uv.lock)
cd frontend && npm install     # frontend deps
cp .env.example .env           # fill in secrets, see table above
make dev                       # uvicorn :8000 + vite :5173 (vite proxies /api -> :8000)
```

The scheduler is **off by default in dev** (`GRIDIRON_SCHEDULER_ENABLED=false`) so
nothing polls Yahoo/ESPN/the NFL scoreboard in the background while you're working —
trigger a refresh by hand whenever you want fresh data:

```sh
curl -X POST localhost:8000/api/admin/refresh                       # sync_discovery (default job)
curl -X POST "localhost:8000/api/admin/refresh?job=refresh_fantasy" # roster/matchup re-sync + diff/publish
curl -X POST "localhost:8000/api/admin/refresh?job=refresh_nfl_state"
curl -X POST "localhost:8000/api/admin/refresh?job=backup_db"
```

Every run — manual or scheduled — is recorded in `refresh_runs`
(`GET /api/admin/refresh-runs`), which is also what Settings' "Last refresh: Xs ago ·
ok/failed" status line reads.

```sh
make test    # uv run pytest + npm test -- --run
make lint    # ruff + black --check + eslint + prettier --check
make build   # frontend prod bundle -> frontend/dist (served by FastAPI once built)
```

## Background jobs (scheduler)

Four jobs run under APScheduler when `GRIDIRON_SCHEDULER_ENABLED=true` (prod); all
four are also directly invokable via `POST /api/admin/refresh?job=<name>` regardless
of that setting:

- **`sync_discovery`** — daily 06:00 local: rediscovers leagues/teams + probes
  credentials.
- **`refresh_fantasy`** — adaptive cadence: the configured live tier (10/30/60s) while
  a game involving one of your rostered starters is live, 5 min on a game day with
  nothing of yours live yet, 30 min off-day — or **once a day** during the off-season
  (below). Diffs the read model against the previous run and publishes SSE
  `data.changed` for whatever scopes actually moved.
- **`refresh_nfl_state`** — polls ESPN's public scoreboard every 30s (feeds the
  live/game-day/off-day classifier), backing off to **hourly** during the off-season.
- **`backup_db`** — nightly ~03:00: a WAL-safe `sqlite3` online backup to
  `<db-dir>/backups/gridiron-YYYYMMDD.db`, pruning anything older than 7 days. This is
  the app's own safety net; **Time Machine is the second layer** — back up the whole
  `data/` directory (or wherever `GRIDIRON_DB_PATH` points) as you normally would.

**Off-season quiescence**: `refresh_nfl_state` remembers the newest kickoff time it's
ever seen on the scoreboard. Once that watermark is more than 7 days stale — which
only happens once the scoreboard genuinely has nothing new to report, deep in the
off-season — both jobs above back off to their slow cadence automatically, and snap
back the moment next season's games reappear on the scoreboard. In practice this means
you don't have to do anything between the Super Bowl and August; **"just quit it until
August" is equally valid** too, if you'd rather — the LaunchAgent's `KeepAlive` will
just restart it, or `launchctl bootout gui/$(id -u)/com.gridiron.app` for the
off-season and re-bootstrap it (`launchctl bootstrap gui/$(id -u)
~/Library/LaunchAgents/com.gridiron.app.plist`) in August.

## Draft Assistant

A manual-entry companion for one live snake draft, at `/draft`. There is no ESPN
live-draft integration yet — you keep it in step with the real draft yourself — and it
runs on the same single self-hosted iMac process as everything else, so read
"When ESPN breaks mid-draft" below before you're on the clock, not during.

### Import the board

The board (players, tiers, and the slot-1 strategy plan) ships as JSON under
`backend/gridiron/draft_board/` (`players.json`, `league_config.json`,
`strategy_rules.json`, `unpriced_risk.json`), sourced from
`2026_Draft_Board.xlsx` in the same directory. Load it into the DB with:

```sh
uv run python -m backend.gridiron.draft_board import
```

Safe to re-run — it upserts by player name, so re-running after editing the board JSON
(a new sleeper, an updated tier, a corrected ADP) refreshes existing rows in place. It
never touches a player's `espn_player_id`/match state on an existing row, so re-running
mid-draft can't clobber a live ESPN match once phase 5 adds one.

### The manual draft flow

1. Open `/draft` before the draft starts — recommendations, tier alarms, and the
   slot-1 plan (if your configured draft slot is actually 1) are live from pick 1.
2. As each pick happens — yours or anyone else's — find the player on the board and
   tap **Mine** or **Theirs**. That single tap is the only state change the app needs;
   the roster, recommendations, and tier alarms all recompute from the recorded picks.
3. Mis-tapped a player? **Undo last pick**, always visible in the header (no
   scrolling), removes the most recent pick and rewinds the pick counter by one.
4. Drafted players stay visible on the board — greyed out, struck through, tagged with
   who took them and at what pick — instead of disappearing, so you can see the whole
   draft's history at a glance without leaving the screen.

### Correcting the current pick number

"The pick happening right now" is tracked as an explicit number you set, never inferred
by counting how many picks you've entered — a real draft involves skipping picks that
don't matter to you and catching up in bursts, so a count-based guess silently drifts
and every downstream recommendation quietly computes against the wrong pick. If you
fall behind or the number is simply wrong, use the **Set pick #** field in the
current-pick bar to jump straight to the correct overall pick number. That field is the
one correction mechanism — don't try to fix drift by entering picks you didn't actually
see happen.

### When ESPN breaks mid-draft

There's no live ESPN draft-room sync to break yet, but the more important fact is
structural: this is one iMac running one process, not a redundant service. If it
reboots, drops off the tailnet, or the app crashes mid-draft, your live dashboard is
gone until it's back — plan for that, not just for ESPN:

- **Keep a printed copy of the board next to you before the draft starts** — print
  `2026_Draft_Board.xlsx` (or print the `/draft` page itself from the browser). This is
  the actual backstop: you keep drafting off paper with zero interruption while the app
  is down, and catch the app back up afterward rather than the other way around.
- If the app goes down mid-draft: check `~/Library/Logs/gridiron/app.err.log` first
  (see Troubleshooting), restart it with
  `launchctl kickstart -k gui/$(id -u)/com.gridiron.app`, then use **Set pick #** to
  resync the counter to wherever the real draft actually is once you're back — don't
  trust its last-known state, confirm it against the room (or your printed board).
- Every pick is committed to SQLite the moment you tap it, so a restart never loses
  picks already recorded — you only lose whatever happened while it was down, which is
  exactly what the printed board and the pick-number correction above are for.

## Logs

- **launchd's own redirect** (always on): `~/Library/Logs/gridiron/app.log` /
  `app.err.log` — raw stdout/stderr, grows forever, the first place to check if the
  process won't start at all.
- **Rotated app + scheduler log** (`GRIDIRON_LOG_DIR`, prod default
  `~/Library/Logs/gridiron/gridiron.log`): every scheduler run logs exactly one line —
  `job=<name> duration_ms=<n> ok=<bool> error=<...>` — at INFO on success, WARN on
  failure. Rotates at 5 MB, keeps 5 backups.

## Troubleshooting

- **ESPN shows "not connected" / rosters stop updating** — ESPN's `SWID`/`espn_s2`
  cookies expire periodically (weeks, not days, but it happens). `meta.platforms.espn`
  on any `/api/teams*` response (and the Settings → Connected Platforms row) will show
  `error: "auth_required"`. Fix: log into ESPN Fantasy in a browser, grab fresh
  `SWID`/`espn_s2` cookie values, and re-enter them in Settings → ESPN Credentials.
- **Yahoo OAuth fails with a redirect_uri mismatch** — Yahoo requires an *exact* match
  between the registered redirect URI and `GRIDIRON_BASE_URL` +
  `/api/connections/yahoo/callback`. Check: (1) both dev and prod URIs are registered
  on the Yahoo app (see Prerequisites), (2) the `.env` you're actually running against
  has `GRIDIRON_BASE_URL` matching the URL you're hitting the app through exactly
  (http vs https, hostname, no trailing slash), (3) no stale browser tab mid-flow
  against a since-changed URL.
- **App won't start / crashes on boot** — check `~/Library/Logs/gridiron/app.err.log`
  first (raw stderr, includes Python tracebacks), then `gridiron.log` if
  `GRIDIRON_LOG_DIR` is set. `launchctl print gui/$(id -u)/com.gridiron.app` shows the
  LaunchAgent's own state (last exit code, whether it's currently running).
- **Tailscale Serve / cert issues** — `tailscale serve status` shows what's currently
  proxied. Tailscale auto-renews the `ts.net` cert; if the browser complains about it
  anyway, `sudo tailscale cert <imac>.<tailnet>.ts.net` forces a renewal, and
  `tailscale serve --bg 8000` re-establishes the proxy if it somehow got torn down
  (e.g. after a Tailscale upgrade).
- **Scheduler seems to have stopped polling** — check `GET /api/admin/refresh-runs`
  for recent entries first; if the gaps match the off-season back-off cadence above,
  that's working as intended, not broken.

## Escape hatches

Neither of these is set up by default — the tailnet-only design (no auth on
`/api/admin/*`, `/api/events`, etc., on the assumption that only trusted tailnet
devices can ever reach them) means turning on either changes the app's trust model.
Add real auth in front before doing either.

- **Public access without putting a device on the tailnet** (e.g. sharing with someone
  who isn't) — put a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
  in front of `localhost:8000` instead of (or alongside) `tailscale serve`, behind
  Cloudflare Access or an API-layer auth change.
- **Outgrowing a single SQLite file / moving off the iMac to a VPS** — the ORM models
  and Alembic migrations (`backend/alembic/`) are already plain, dialect-neutral
  SQLAlchemy (no SQLite-specific column types or raw SQL), so a move to Postgres is
  mostly a `backend/gridiron/db.py` connection-string change (swap `aiosqlite` for
  `asyncpg`, point at a `DATABASE_URL`-style setting instead of `GRIDIRON_DB_PATH`)
  plus `alembic upgrade head` against the new database, not a rewrite. `backup_db`'s
  `sqlite3`-specific online-backup step would need swapping for `pg_dump` at that point.

See `openspec/` for the full proposal, design, and task plan.
