## ADDED Requirements

### Requirement: NFL game-state detection

The system SHALL determine whether any NFL game is currently live by polling ESPN's free public scoreboard, NOT the Yahoo or ESPN fantasy endpoints. Game-state classification drives the in-process scheduler's refresh cadence and is surfaced to the frontend both in the response envelope (`meta.live_state`) and as an SSE event on transitions.

#### Scenario: Scoreboard refresh

- **WHEN** the scheduler job `refresh_nfl_state` runs (every 30 seconds)
- **THEN** the system GETs `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`, parses each event's `status.type.state` (`pre` | `in` | `post`) and `status.type.detail` (clock + period), upserts the result into the `live_nfl_games` table, and completes within 5 seconds.

#### Scenario: "Live" classification

- **WHEN** at least one event has `state == "in"` and that game contains an NFL team rostered on any of the user's fantasy teams
- **THEN** `live_state` is classified `"live"`, the `refresh_fantasy` job reschedules to the live cadence (default 30 s), and a `live_state.changed` SSE event is published if the classification changed.

#### Scenario: "Game-day" classification

- **WHEN** any event with `state == "in"` exists OR the current local date matches a regular-season game day (Thu / Sun / Mon)
- **THEN** `live_state` is classified at least `"game_day"` and the `refresh_fantasy` job runs at the game-day cadence (default 5 min).

### Requirement: In-process adaptive refresh scheduler

The system SHALL refresh the backend cache from an APScheduler `AsyncIOScheduler` started inside the FastAPI process's lifespan hook. There SHALL be no external cron infrastructure and no scheduling-related authentication secret. Refresh jobs SHALL be idempotent.

#### Scenario: Registered jobs

- **WHEN** the process boots
- **THEN** the scheduler registers:
  - `refresh_nfl_state` — every 30 s — refreshes `LiveNflGame[]`.
  - `refresh_fantasy` — adaptive — refreshes Yahoo + ESPN data for enabled leagues, then reschedules itself from the current `live_state`: live tier (default 30 s, user-tunable), 5 min on `game_day`, 30 min on `off_day`.
  - `sync_discovery` — daily 06:00 local — refreshes league/team discovery and verifies credentials.

#### Scenario: Run recording

- **WHEN** any scheduler job completes (success or failure)
- **THEN** a row is written to `refresh_runs` (`job_name`, `run_at`, `ok`, `error`, `duration_ms`), queryable via `GET /api/admin/refresh-runs` for the Settings page's "Last refresh" line.

#### Scenario: Adaptive backoff on platform errors

- **WHEN** an upstream returns 429 or 5xx during a refresh run
- **THEN** the run records the error with the platform's `cooldown_until` set to `now() + 5 minutes`. Subsequent runs within the cooldown window skip that platform.

#### Scenario: Manual trigger

- **WHEN** the frontend POSTs `/api/admin/refresh` (optionally `?job=<name>`)
- **THEN** the named job (default `refresh_fantasy`) runs immediately. No secret is required — the endpoint is reachable only from tailnet devices or localhost.

#### Scenario: Off-season quiescence

- **WHEN** the NFL scoreboard has shown no scheduled games for more than 7 consecutive days
- **THEN** `refresh_fantasy` and `refresh_nfl_state` suspend and only `sync_discovery` continues, until the scoreboard shows upcoming games again.

### Requirement: SSE push protocol

The system SHALL push change notifications to connected clients over Server-Sent Events at `GET /api/events`. SSE carries **signals**; data always flows through the REST envelope — clients refetch the named scopes rather than parsing payloads from the stream.

#### Scenario: Change detection and publication

- **WHEN** a refresh run writes data to the cache
- **THEN** the differ compares the new snapshot with the previous one and publishes a `data.changed` event to the in-process bus containing the changed scopes (e.g., `["teams", "team:yahoo:nfl.l.123456.t.4"]`) and the new `as_of` timestamp. Runs that change nothing publish nothing.

#### Scenario: Event stream contract

- **WHEN** a client is connected to `/api/events`
- **THEN** it receives events of exactly these types: `data.changed { scopes, as_of }`, `live_state.changed { live_state }`, `tier.change { live_tier_seconds }`, and `heartbeat { at }` every 15 seconds. On connect, the server immediately sends the current `live_state.changed` so a fresh client needs no separate state fetch.

#### Scenario: Client fan-out

- **WHEN** N clients are connected and an event is published
- **THEN** every client receives the event (per-client asyncio queues); a slow or dead client's queue is dropped after disconnect without blocking other clients or the scheduler.

### Requirement: Frontend live-update protocol

The frontend SHALL consume `/api/events` via `EventSource` and translate `data.changed` scopes into TanStack Query invalidations, so updates render within ~1 second of a cache write. Timer-based polling SHALL exist only as a degraded fallback.

#### Scenario: Scope-to-query mapping

- **WHEN** a `data.changed` event arrives with scopes
- **THEN** the client invalidates the TanStack Query keys matching those scopes for the currently-viewed week only (`teams` → `['teams', week]`; `team:{id}` → `['team', id, week]` and its h2h/season variants), triggering refetches from the local REST API.

#### Scenario: Reconnect and fallback

- **WHEN** the SSE connection drops (process restart, phone sleeping, network change)
- **THEN** `EventSource` reconnects with backoff; while disconnected longer than 30 s the sidebar footer shows "Live connection lost — retrying" and a 5-minute `refetchInterval` fallback activates. On `visibilitychange` to visible, the client refetches active queries immediately and re-establishes the stream.

#### Scenario: Past weeks are static

- **WHEN** the user is viewing a week older than the current week
- **THEN** `data.changed` events do not invalidate that week's queries — historical data is immutable and refetching it is wasted work.

### Requirement: Response-shape contract

The system SHALL return enough state on each REST response that the frontend can surface freshness without a separate endpoint.

#### Scenario: Response envelope

- **WHEN** the frontend GETs any of `/api/teams`, `/api/teams/{id}`, `/api/teams/{id}/h2h`, `/api/teams/{id}/season`
- **THEN** the response body includes the requested data plus an envelope:
  ```
  {
    "data": <endpoint-specific>,
    "meta": {
      "live_state": "live" | "game_day" | "off_day",
      "as_of": "<ISO timestamp of the cached row>",
      "next_refresh_at": "<ISO timestamp of the scheduler's next planned run>",
      "platforms": { "yahoo": { "ok": true }, "espn": { "ok": false, "error": "auth_required" } }
    }
  }
  ```

#### Scenario: HTTP cache headers

- **WHEN** any `/api/teams*` endpoint responds
- **THEN** it sets `Cache-Control: private, max-age=15, stale-while-revalidate=30`, so bursts of invalidation-driven refetches across multiple open tabs coalesce in the browser cache.

### Requirement: Freshness signaling

The frontend SHALL surface a "Last updated Xs ago" indicator and pulse animation on values that just changed, driven by SSE-triggered refetches.

#### Scenario: Last-updated counter

- **WHEN** any response is received
- **THEN** the sidebar footer's `Last updated …` label is computed from `now() - response.meta.as_of` and ticks upward in real time. After 90 seconds past the expected refresh cadence without fresh data, the label switches to `Stale` styling (`color: var(--text-secondary)` → `var(--live)`).

#### Scenario: Pulse on changed values

- **WHEN** a refetch delivers a numeric value (`actual_points`, `score`, `proj`, etc.) that differs from the previously-rendered value
- **THEN** the new value renders with a 600 ms pulse animation (opacity 0.4 → 1) so the change is noticeable without being distracting. Diffing is implemented by `useChangedValuePulse(currentValue)` which compares against a ref of the prior render; it does not fire on first render or on reconnect refetches that deliver unchanged values.

#### Scenario: Backend refresh failures surface within one tick

- **WHEN** refresh runs have been failing for more than 10 minutes
- **THEN** the frontend banner reads "Live updates paused — last sync N min ago", derived from `meta.as_of` staleness — no separate health endpoint required.
