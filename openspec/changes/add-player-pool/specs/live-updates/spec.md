## MODIFIED Requirements

### Requirement: In-process adaptive refresh scheduler

The system SHALL refresh the backend cache from an APScheduler `AsyncIOScheduler` started inside the FastAPI process's lifespan hook. There SHALL be no external cron infrastructure and no scheduling-related authentication secret. Refresh jobs SHALL be idempotent.

#### Scenario: Registered jobs

- **WHEN** the process boots
- **THEN** the scheduler registers:
  - `refresh_nfl_state` — every 30 s — refreshes `LiveNflGame[]`.
  - `refresh_fantasy` — adaptive — refreshes Yahoo + ESPN data for enabled leagues, then reschedules itself from the current `live_state`: live tier (default 30 s, user-tunable), 5 min on `game_day`, 30 min on `off_day`.
  - `refresh_player_pool` — every 6 h, fixed — refreshes the free-agent/waiver pool and season projections for every league where the user owns a team.
  - `sync_discovery` — daily 06:00 local — refreshes league/team discovery and verifies credentials.

#### Scenario: Pool refresh cadence is fixed, not adaptive

- **WHEN** `refresh_player_pool` is scheduled
- **THEN** its interval SHALL be fixed and SHALL NOT be rescheduled from `live_state`
- **AND** this is deliberate: the job fans out across every league at roughly 3.7 MB per league, and attaching it to `refresh_fantasy`'s live-tier cadence would issue that fan-out up to 120 times per hour during games, for data that only changes when waiver claims process.

#### Scenario: Partial pool failure is reported, not fatal

- **WHEN** a pool refresh encounters entries it cannot map
- **THEN** the run completes, persists what it could, and records the skip count in the run's summary, so degradation from an upstream schema change is visible in `GET /api/admin/refresh-runs` rather than silent.

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
- **THEN** `refresh_fantasy`, `refresh_nfl_state`, and `refresh_player_pool` suspend and only `sync_discovery` continues, until the scoreboard shows upcoming games again.
