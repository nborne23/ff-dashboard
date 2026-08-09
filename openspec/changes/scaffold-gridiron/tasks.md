## 1. Project scaffolding + design system extraction + first iMac deploy

> **Deliverable:** `make dev` runs the empty project locally on the M4 (Vite SPA + FastAPI `/api/health`); `make deploy` ships it to the iMac where launchd keeps it alive and Tailscale Serve exposes it at `https://<imac>.<tailnet>.ts.net`. Vite renders an empty 5-route React app with sidebar + topbar + aurora wired to design tokens. **Risk:** trivial, except one-time iMac setup (uv, Tailscale, pmset, launchd) which is scripted. **Test:** `curl https://<imac>.<tailnet>.ts.net/api/health` from the phone (on tailnet) returns `{"ok": true}`; opening the URL shows the shell with all five sidebar nav items working and the per-screen aurora color shifting. Frontend tasks (1.4–1.7) and backend/deploy tasks (1.2, 1.8, 1.9) are parallelizable after 1.1.

- [x] 1.0 Import the design source: connect the claude_design MCP (`https://api.anthropic.com/v1/design/mcp`, authenticate via `/design-login`) and import project `https://claude.ai/design/p/1692dcc6-8418-4f8f-9139-5d19358beaca?file=GridIron.html`. `GridIron.html` is the pixel-fidelity reference implemented by this change — extract its `styles.css` tokens and `primitives.jsx` (consumed by 1.4/1.5) and keep a copy under `design/` in the repo so later visual-diff tasks (4.9, 10.9) don't depend on the MCP being reachable.
- [x] 1.1 Initialize root repo: `pyproject.toml` + `.python-version` (uv-managed), `.env.example`, `.gitignore` (includes `data/`), `README.md`, `Makefile` with `dev`, `lint`, `test`, `build`, `deploy` targets.
- [x] 1.2 Backend scaffold: uv deps — fastapi, uvicorn, httpx, pydantic, pydantic-settings, sqlalchemy[asyncio], aiosqlite, alembic, apscheduler, sse-starlette, cryptography, authlib, ruff, black, pytest, pytest-asyncio, respx. `backend/main.py` app factory with `/api/health` returning `{"ok": true}`, lifespan hook stub for the scheduler, and static mounting of `frontend/dist` when present.
- [x] 1.3 Frontend scaffold: `frontend/package.json` with React 18, react-dom, react-router-dom, @tanstack/react-query, zustand, vite, typescript, vitest, @testing-library/react, eslint, prettier. `vite.config.ts` with `/api` proxy to `http://localhost:8000` for local dev.
- [x] 1.4 Lift design tokens: copy the prototype's `:root` block into `frontend/src/styles/tokens.css`; copy global rules (body, scrollbars, large-title, card, pill, etc.) into `frontend/src/styles/global.css`. Verify against the bundle line-by-line.
- [x] 1.5 Port SVG primitives from `primitives.jsx` into `frontend/src/components/primitives/` as TypeScript components: `ActivityRing`, `Sparkline`, `BarChart`, `HorizBar`, `DayRings`, `Icons`. Add a Vitest snapshot test per primitive.
- [x] 1.6 Build the persistent shell: `Sidebar` (with platform-dot sub-items), `Topbar` (week navigator + DayRings + live badge), `Aurora` (per-screen color via `--aurora-color`). Wire `useTweaks()` Zustand store + `TweaksPanel`.
- [x] 1.7 Wire React Router 6 with the five routes (`/`, `/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`, `/settings`). Each screen renders a placeholder.
- [x] 1.8 iMac one-time setup script `deploy/setup-imac.sh`: install uv + node (Homebrew), clone repo, `uv sync`, write `.env`, `pmset -c sleep 0 && sudo pmset autorestart 1`, enable auto-login note, `tailscale serve --bg 8000`, install + load `deploy/com.gridiron.app.plist` (RunAtLoad, KeepAlive, logs to `~/Library/Logs/gridiron/`).
- [x] 1.9 `deploy/deploy.sh` + `make deploy`: ssh over the tailnet → `git pull`, `uv sync`, `npm ci && npm run build` in `frontend/`, `alembic upgrade head` (no-op until Phase 2), `launchctl kickstart -k` the agent. Verify health endpoint after restart.
- [ ] 1.10 Acceptance test: `make dev` boots locally; `make deploy` succeeds from the M4; phone on tailnet loads the shell over HTTPS; reboot the iMac and confirm the app comes back without keyboard/mouse.

## 2. Yahoo OAuth + ESPN cookie auth (real leagues)

> **Deliverable:** Yahoo OAuth + ESPN cookie flows working end-to-end against the user's real leagues, both in local dev and on the deployed tailnet URL. **Risk:** Yahoo OAuth needs two redirect URIs registered (localhost dev + `.ts.net` prod); ESPN cookies expire mid-test. **Test:** open Settings on the iMac URL from the laptop, click "Connect Yahoo", complete browser OAuth, see "Connected as ..."; paste real ESPN cookies, click "Test Connection", see "Connected · 4 minutes ago".

- [x] 2.1 Backend `gridiron/models/connections.py` SQLAlchemy ORM + first Alembic migration creating `connections` table with encrypted token columns. Migration runs via `alembic upgrade head` in `deploy.sh` and on `make dev` bootstrap.
- [x] 2.2 `gridiron/services/credentials.py`: Fernet-based encrypt/decrypt using key from `GRIDIRON_SECRET_KEY`; `CredentialDecryptError` typed exception.
- [x] 2.3 `gridiron/db.py`: SQLAlchemy async engine for `sqlite+aiosqlite:///data/gridiron.db` with WAL mode and `busy_timeout=5000` set on connect; async session factory; `data/` auto-created on boot.
- [x] 2.4 `gridiron/platforms/yahoo/oauth.py`: authorization-URL generation with HMAC-signed `state`; callback handler exchanging `code` for tokens.
- [x] 2.5 `gridiron/platforms/yahoo/client.py`: httpx `AsyncClient` wrapper that injects `Authorization: Bearer …`, intercepts 401 → refresh → retry once, intercepts 429/999 → exponential backoff (1/2/4s, 3 retries), raises typed `AuthRequiredError` / `RateLimitedError`.
- [x] 2.6 `gridiron/platforms/espn/client.py`: httpx wrapper that sets `Cookie: SWID=...; espn_s2=...`, marks platform `auth_required` on 401/403, base URL configurable via `ESPN_BASE_URL` env var (default `https://lm-api-reads.fantasy.espn.com`).
- [x] 2.7 `gridiron/api/connections.py`: `GET /api/connections`, `POST /api/connections/yahoo/start`, `GET /api/connections/yahoo/callback`, `POST /api/connections/espn/test`, `DELETE /api/connections/{platform}`.
- [ ] 2.8 Register one Yahoo developer app with both redirect URIs as https tailnet URLs (Yahoo rejects plain `http://` redirect URIs): `https://<dev-machine>.<tailnet>.ts.net/api/connections/yahoo/callback` (dev, requires `tailscale serve --bg 8000` on the dev machine) and `https://<imac>.<tailnet>.ts.net/api/connections/yahoo/callback` (prod). Put client ID/secret in the M4's `.env` and the iMac's `.env`; set `GRIDIRON_BASE_URL` per machine to its https tailnet URL so the OAuth flow builds the right redirect.
- [x] 2.9 Settings screen — backend integration: `ConnectionsCard` calls `GET /api/connections` via TanStack Query; `EspnCredentialsCard` POSTs to `/api/connections/espn/test`; Yahoo connect button opens OAuth URL in same tab.
- [ ] 2.10 Acceptance test: Yahoo OAuth round-trips on the deployed tailnet URL; ESPN cookies persist across `make deploy` restarts (DB survives redeploys); toggling Yahoo off deletes tokens and the row reverts to "Connect Yahoo".

## 3. League / team discovery + normalization + persistence

> **Deliverable:** every Yahoo + ESPN team the user owns is fetched, mapped to the normalized model, and persisted in SQLite. **Risk:** Yahoo's `game_key` resolution is fiddly; ESPN slot-id translation table needs every position the user has. **Test:** trigger a manual sync via `curl -X POST https://<imac>.<tailnet>.ts.net/api/admin/refresh?job=sync_discovery`, then `sqlite3 data/gridiron.db 'select name from teams'` shows every team. Mapper tasks (3.4–3.8) are parallelizable per-platform.

- [x] 3.1 Backend `gridiron/models/`: SQLAlchemy ORM for `League`, `Team`, `Player`, `RosterSlot`, `Matchup`, `MatchupSlot`, `SeasonWeek`, `LiveNflGame`, `HttpCache`, `RefreshRun`, `Headshot`. Alembic migration. Keep SQL dialect-neutral (raw JSON as TEXT) so a future Postgres move is connection-string-only.
- [x] 3.2 `gridiron/schemas/`: Pydantic models matching the TypeScript interfaces in `design.md` D12, including the `Envelope<T>` wrapper and `SseEvent` union. Configure FastAPI to use these for response models so OpenAPI is accurate.
- [x] 3.3 `gridiron/services/cache.py`: `HttpCache` get/set/invalidate with `(platform, endpoint, params_hash) → (raw_json, expires_at)`. Reads NEVER fetch on miss — they return whatever is cached or empty.
- [x] 3.4 `gridiron/platforms/yahoo/client.py` methods: `resolve_game_key()`, `list_leagues()`, `get_team()`, `get_roster()`, `get_matchup()`. Each call is cache-checked.
- [x] 3.5 `gridiron/platforms/yahoo/mapper.py`: pure functions `map_league`, `map_team`, `map_roster`, `map_matchup`. Unit tests against captured fixtures from the user's real leagues.
- [x] 3.6 `gridiron/platforms/espn/client.py`: `get_league(league_id)`, `get_roster()`, `get_matchup()`. Cache-checked. Single helper for `view` parameter stacking.
- [x] 3.7 `gridiron/platforms/espn/slot_table.py`: `lineupSlotId → "QB" | "RB1" | ...` lookup; raises on unknown ID.
- [x] 3.8 `gridiron/platforms/espn/mapper.py`: pure-function mappers, fixture-tested.
- [x] 3.9 `gridiron/services/fantasy_service.py`: `list_teams(week)`, `get_team()`, `get_h2h()`, `get_season()`. Each fans out across both platforms in parallel via `asyncio.gather` with `return_exceptions=True`; per-platform errors annotate `meta.platforms` rather than propagating.
- [x] 3.10 `gridiron/api/teams.py`: REST endpoints implementing the contracts in `fantasy-data-model` spec, returning the envelope `{ data, meta }`. Set `Cache-Control: private, max-age=15, stale-while-revalidate=30` headers.
- [x] 3.11 `gridiron/services/headshots.py` + `gridiron/api/headshots.py`: fetch-once to `data/headshots/{platform}/{player_id}.png`, serve via `FileResponse` with `Cache-Control: public, max-age=86400, immutable`; silhouette PNG written on upstream 404 (negative cache).
- [x] 3.12 First scheduler job: `gridiron/scheduler.py` registers `sync_discovery` (daily 06:00) calling `fantasy_service.refresh_discovery()`; `gridiron/api/admin.py` adds `POST /api/admin/refresh?job=...` to trigger any job immediately (no secret — tailnet-only reachability).
- [ ] 3.13 Acceptance test: hitting `GET /api/teams?week={current}` returns ≥ 1 team per platform; envelope `meta.live_state` populated; second hit within 15 s served from browser cache (DevTools shows 304/disk cache).

## 4. Dashboard screen with real data (scheduler-refreshed cache)

> **Deliverable:** Dashboard renders all the user's teams with real names, scores, opponents, sparklines, and the Insights rail. The frontend uses TanStack Query with a single fetch on mount + manual refresh button — SSE arrives in Phase 8. The discovery job from Phase 3 keeps the cache warm. **Risk:** sparkline data needs past N weeks per team; Top Performer needs a cross-team query. **Test:** open `/`, see exactly the prototype's layout but with real team names; click refresh after a stat correction lands in cache and see the new value. Tile tasks (4.3–4.6) are parallelizable.

- [x] 4.1 Frontend `api/client.ts` parsing the `{ data, meta }` envelope; sets `staleTime: 15_000`.
- [x] 4.2 Frontend hooks `useTeams(week)`, `useTeam(id, week)`, `useTeamH2H(id, week)`, `useTeamSeason(id)` — no live updates yet (added in Phase 8).
- [x] 4.3 Build `screens/Dashboard/TeamCard.tsx` matching the prototype exactly.
- [x] 4.4 Build `screens/Dashboard/InsightTopPerformer.tsx` — backend computes the highest-scoring active player across all of the user's teams this week + position median for the comparison bar.
- [x] 4.5 Build `screens/Dashboard/InsightWeeklyTrend.tsx` — backend computes 6-week aggregate average + delta.
- [x] 4.6 Build `screens/Dashboard/InsightLiveGames.tsx` — pulls from `/api/nfl/scoreboard`, filters to games containing the user's rostered NFL teams.
- [x] 4.7 Wire the topbar refresh button to `POST /api/admin/refresh` then `queryClient.invalidateQueries(['teams'])`.
- [x] 4.8 Implement loading skeleton + error state + connect-required empty state for each tile.
- [ ] 4.9 Acceptance test: side-by-side compare the prototype's Dashboard screenshot with the production Dashboard rendered from real data — every alignment, color, font weight, and spacing should match.

## 5. My Team + Head-to-Head screens

> **Deliverable:** clicking a team card navigates to `/team/:teamId`, showing the full roster, side cards, and a working week selector; the H2H sidebar item navigates to `/team/:teamId/h2h`. **Risk:** the H2H slot comparison needs both teams' rosters joined by slot — alignment is non-trivial when sides have different FLEX positions. **Test:** open My Team for the user's primary team in week N, see the live row tinted pink, the score ring at the right percentage, and the Move-style intra-day chart. My Team (5.1–5.5) and H2H (5.6–5.8) are parallelizable tracks.

- [x] 5.1 `screens/MyTeam/RosterTable.tsx`: Starters + Bench sections, live-row tint, OUT styling, +/– delta coloring.
- [x] 5.2 `screens/MyTeam/ScoreCard.tsx`: ActivityRing of `actual / projected`.
- [x] 5.3 `screens/MyTeam/WeeklyChartCard.tsx`: BarChart with dashed reference line at projected pace.
- [x] 5.4 `screens/MyTeam/RecordCard.tsx`: cumulative W/L sparkline + W/L pill grid.
- [x] 5.5 Wire the topbar week navigator to refetch via `useTeam(id, week)`.
- [x] 5.6 `screens/HeadToHead/H2HRings.tsx`: 200px ActivityRing with two concentric tracks + lead differential center label.
- [x] 5.7 `screens/HeadToHead/H2HTable.tsx`: slot-by-slot table with mirrored opponent column and signed-differential chips.
- [x] 5.8 `screens/HeadToHead/RemainingPlayersCard.tsx` and `ProjectedFinalCard.tsx`: backend computes remaining-player count + range using `σ ≈ 12 pts per remaining player` + confidence percentage.
- [ ] 5.9 Acceptance test: navigate Dashboard → MyTeam → H2H, the data is consistent across screens for the same week.

## 6. Season screen

> **Deliverable:** full-season weekly bar chart + highlights + record donut + week-by-week history. **Risk:** highlights computation (longest win streak, season-high week, most-started player) has off-by-one traps. **Test:** highlights match what the user sees if they manually scan the season. 6.2–6.5 are parallelizable once 6.1 lands.

- [x] 6.1 Backend `services/fantasy_service.get_season(team_id)` returns weeks + highlights computed in SQL.
- [x] 6.2 `screens/Season/SeasonChart.tsx`: SVG bar chart, cyan wins / pink losses, ghost opponent bars, current-week column overlay, average-points dashed line.
- [x] 6.3 `screens/Season/HighlightCard.tsx` parameterized by accent + icon + label + value + sub.
- [x] 6.4 `screens/Season/RecordDonut.tsx`: 180px ActivityRing + center label.
- [x] 6.5 `screens/Season/WeekHistory.tsx`: scrolling list, current-week highlighted.
- [ ] 6.6 Acceptance test: every SEASON entry from the prototype data is replaced with real data; numbers match Yahoo/ESPN web UIs.

## 7. Settings screen with connection management

> **Deliverable:** Settings screen wired end-to-end — Yahoo + ESPN connection toggles, ESPN cookie fields, live-tier selector, league enable/disable toggles, data management buttons. **Risk:** Yahoo toggle behavior is destructive (delete tokens) — needs a confirm dialog. **Test:** disconnect ESPN, refresh page, see "Connect ESPN"; reconnect with the previously-stored cookies. Card tasks (7.1–7.6) are parallelizable.

- [x] 7.1 `screens/Settings/ConnectionsCard.tsx`: rows for Yahoo + ESPN with display name + last-verified + switch.
- [x] 7.2 `screens/Settings/EspnCredentialsCard.tsx`: SWID + espn_s2 fields + Test Connection button.
- [x] 7.3 `screens/Settings/EspnLeaguesCard.tsx`: list of discovered ESPN leagues with per-league enable toggle (`leagues.is_enabled` column).
- [x] 7.4 `screens/Settings/PreferencesCard.tsx`: live-tier segmented control (`10s | 30s | 1m` — now real backend refresh cadences; 30 s default) + the three notification toggles (persisted but inert).
- [x] 7.5 `screens/Settings/AppearanceCard.tsx`: theme + accent picker (decorative for v1).
- [x] 7.6 `screens/Settings/DataManagementCard.tsx`: Refresh all data, Clear cache, Export JSON, Disconnect all platforms (with confirm).
- [x] 7.7 Wire backend endpoints: `POST /api/settings/live-tier` (reschedules the running `refresh_fantasy` job + emits `tier.change` SSE event once Phase 8 lands), `POST /api/admin/refresh`, `DELETE /api/cache`, `GET /api/export.json`.
- [ ] 7.8 Acceptance test: click Refresh → 1 round of upstream Yahoo + ESPN calls, watch `meta.as_of` update to now; click Clear cache → next data fetch shows empty data until the next scheduler tick.

## 8. Adaptive refresh scheduler + SSE push

> **Deliverable:** open the dashboard during a live game; values update within seconds of the 30 s backend refresh without any user action; the "Last updated 12s ago" indicator ticks; the pulse animation fires on changed values. **Risk:** highest-risk phase — the scheduler cadence, snapshot diffing, and SSE lifecycle must compose; mobile Safari suspends EventSource in background tabs. **Test:** during an actual NFL game window, watch the dashboard on the laptop and the phone for 5 minutes and confirm values change with the right cadence and visual feedback; kill the backend mid-view and confirm the disconnect banner + reconnect. Backend (8.1–8.5) and frontend (8.6–8.9) are parallelizable tracks against the `SseEvent` contract.

- [x] 8.1 `gridiron/services/live_state.py`: classifier from `LiveNflGame[]` → `"live" | "game_day" | "off_day"`, scoped to "live involves user players".
- [x] 8.2 `gridiron/platforms/nfl_scoreboard.py`: client for ESPN public scoreboard; map to `LiveNflGame[]`. Scheduler job `refresh_nfl_state` every 30 s.
- [x] 8.3 `gridiron/scheduler.py`: `refresh_fantasy` job that refetches all enabled leagues, then reschedules itself from current `live_state` (30 s live / 5 min game day / 30 min off-day; live tier read from settings). Records every run in `refresh_runs`.
- [x] 8.4 `gridiron/services/events.py` (asyncio pub/sub bus with per-client queues) + `gridiron/services/differ.py` (snapshot diff → changed scopes). Cache writes publish `data.changed` with scopes + `as_of`; live-state transitions publish `live_state.changed`.
- [x] 8.5 `gridiron/api/events.py`: `GET /api/events` via sse-starlette — replays current `live_state` on connect, streams bus events, 15 s heartbeat, cleans up queues on disconnect. Verify N concurrent clients each get every event.
- [x] 8.6 Frontend `api/events.ts` — `useLiveEvents()`: EventSource wiring, maps `data.changed` scopes to TanStack Query key invalidations, handles `tier.change` + `live_state.changed`, auto-reconnect with backoff, exposes connection status to the shell.
- [x] 8.7 Frontend `hooks/useChangedValuePulse.ts`: diffs current value vs `useRef` of prior value; tags `data-just-changed`; CSS animation fires once.
- [x] 8.8 Frontend `hooks/useFreshness.ts`: ticks `Last updated Xs ago` from `meta.as_of`; switches to `Stale` styling after 90 s.
- [x] 8.9 Frontend fallback: while SSE is disconnected > 30 s, show "Live connection lost — retrying" in the sidebar footer and enable a 5-minute `refetchInterval`; immediate refetch + reconnect on `visibilitychange` back to visible.
- [ ] 8.10 Acceptance test: deploy to the iMac, open during a live game window on laptop + phone, watch for 5 minutes, confirm: values change within ~1 s of each 30 s refresh, "Last updated" ticks, pulse fires on changed values, backgrounding the phone tab then refocusing recovers instantly, killing the process shows the disconnect banner and `launchctl` restart reconnects clients.

## 9. Week selector wired to historical data

> **Deliverable:** topbar Week back/forward + the My Team segmented control fetch historical weeks for both platforms; data is cached in SQLite. **Risk:** ESPN historical-week semantics — `scoringPeriodId` (NFL week) and `matchupPeriodId` (fantasy matchup index) sometimes diverge in playoffs. **Test:** click back to week 1, see week-1 data; click forward through every week without missing data.

- [x] 9.1 `useTeams`, `useTeam`, `useTeamH2H` keyed by `(week, ...)` so changing week issues a fresh query.
- [x] 9.2 Wire `Topbar` `onWeekChange` to a Zustand store + URL search param (`?week=14`) so refresh preserves week.
- [x] 9.3 Backend `services/fantasy_service` accepts `week` everywhere; passes to platform clients.
- [x] 9.4 ESPN historical: include `mBoxscore` view for past weeks so per-player scoring is available.
- [x] 9.5 Lock past weeks: rosters older than current week are immutable — bump cache TTL to 24 h once `current_week > week + 1`. SSE events never fire for past weeks.
- [ ] 9.6 Acceptance test: navigate Week 1 → Week 7 → Week 14 — distinct data each time; second visit is cache-only (DevTools shows 0 upstream calls).

## 10. Polish: loading / error / empty states + animations

> **Deliverable:** every screen has loading, error, and empty states; pulse feels native; the sidebar's "Last updated" is satisfying to watch. **Risk:** scope creep. **Test:** disconnect both platforms in Settings, every screen shows a graceful empty state directing to Settings.

- [x] 10.1 Loading: every TanStack Query loading state renders a skeleton matching the final component's dimensions (no layout shift). Reuse a `<Skeleton />` primitive.
- [x] 10.2 Error: every error state renders an `<ErrorCard />` with `var(--espn)` icon + typed error message + Retry.
- [x] 10.3 Empty: when both platforms disconnected, all data screens show a single full-page empty state pointing to `/settings`.
- [x] 10.4 Pulse animation tuning: confirm `useChangedValuePulse` triggers only on numeric change, not on initial render or SSE reconnect refetches. Side-by-side compare with the prototype that the duration / easing feels right.
- [x] 10.5 Aurora intensity slider in TweaksPanel adjusts the gradient strength; sidebar width slider adjusts layout live.
- [x] 10.6 Day-of-week activity rings in topbar are computed from real per-day scoring; they update via SSE like everything else.
- [x] 10.7 Vitest: `useLiveEvents` invalidates exactly the keys named in a `data.changed` event; `useChangedValuePulse` does not fire on first render.
- [x] 10.8 Backend integration test: spin up FastAPI in test mode with fixture-based platform clients, hit `/api/teams?week=14`, assert envelope + Pydantic schema; open `/api/events`, trigger a refresh, assert the `data.changed` event arrives.
- [ ] 10.9 Final visual diff pass: render every screen at 1440px / 1024px / 768px (the phone-over-Tailscale case); compare to prototype.
- [x] 10.10 Document `README.md`: prerequisites (uv, node, Tailscale on all devices, Yahoo developer app), one-time iMac setup via `deploy/setup-imac.sh`, env-var setup, redirect URI registration, dev workflow (scheduler off by default, manual refresh endpoint), troubleshooting (ESPN cookie expiry, Yahoo redirect URI mismatch, launchd log locations, Tailscale Serve cert renewal), and the documented-not-built escape hatches (Cloudflare Tunnel for public access; VPS/Postgres migration).
- [ ] 10.11 Acceptance: ship v1.

## 11. iMac deployment hardening + observability

> **Deliverable:** the iMac deployment is reliable and observable; refresh failures don't silently rot; the machine survives reboots, power cuts, and off-season neglect. **Risk:** macOS quirks (sleep, login sessions, launchd env) surface only on the real machine. **Test:** pull the iMac's power cord mid-game-window; within ~3 minutes of power restore the dashboard is live again with no keyboard touched.

- [ ] 11.1 Verify unattended-recovery path end-to-end: `pmset autorestart 1`, auto-login, LaunchAgent `RunAtLoad` + `KeepAlive`, Tailscale up at login, `tailscale serve` config persisted. Test by power-cycling.
- [x] 11.2 Refresh observability: `refresh_runs` exposed via `GET /api/admin/refresh-runs`; "Last refresh: 42s ago · ok" line on the Settings page; WARN-level log + SSE `data.changed` suppression when a run fails (stale `as_of` drives the UI banner).
- [x] 11.3 Log hygiene: app logs to `~/Library/Logs/gridiron/` with size-based rotation (loguru or logging.handlers); scheduler logs one line per run (job, duration, ok/error).
- [x] 11.4 Nightly SQLite backup: `sqlite3 data/gridiron.db '.backup data/backups/gridiron-%Y%m%d.db'` via the scheduler, 7-day rotation; document Time Machine as the second layer.
- [ ] 11.5 Resource sanity check on the 2019 iMac: confirm steady-state RSS < 300 MB and near-zero CPU between ticks; no fan spin during live-game cadence.
- [x] 11.6 Verify cache headers: `/api/teams*` (`private, max-age=15, stale-while-revalidate=30`), `/api/headshots/*` (`public, max-age=86400, immutable`), `frontend/dist` assets hashed + immutable, `index.html` no-cache.
- [x] 11.7 Off-season behavior: scheduler drops to daily discovery only when the scoreboard shows no games for > 7 days; README documents "just quit it until August" as equally valid.
- [ ] 11.8 Acceptance: redeploy from a fresh clone with only `.env.example` filled in; confirm the README walkthrough (M4 dev + iMac deploy) produces a working tailnet deployment in < 30 minutes.
