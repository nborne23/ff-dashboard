"""In-process APScheduler wiring (design.md D8) — `sync_discovery` (task 3.12) plus the
Phase 8 adaptive-cadence jobs:

- `refresh_fantasy` — Yahoo/ESPN cache refresh, rescheduling itself from the current
  `live_state` (task 8.3): the configured live tier (10/30/60s, `app_settings`) while
  "live", 5 min for "game_day", 30 min for "off_day" — or once a day, off-season
  (task 11.7).
- `refresh_nfl_state` — ESPN public-scoreboard poll feeding the live_state classifier
  and the SSE differ (task 8.2): 30s normally, backing off to hourly off-season
  (task 11.7).
- `refresh_player_pool` — free-agent/waiver pool + season projections, fixed 6h cadence.
- `refresh_injuries` — ESPN injury-report detail for non-healthy players, fixed 30 min
  (add-player-health).
- `backup_db` — nightly SQLite backup + prune (task 11.4).

Every job run — scheduled or manually triggered via `POST /api/admin/refresh` — goes
through `run_job`, which times the job and writes a `refresh_runs` audit row (success or
failure), per the live-updates spec's "Run recording" scenario, and logs exactly one
summary line (task 11.3).
"""

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.db import async_session_factory, resolve_db_path
from backend.gridiron.errors import GridironError
from backend.gridiron.models import RefreshRun
from backend.gridiron.platforms import espn_injuries, nfl_scoreboard
from backend.gridiron.schemas.events import LiveStateChangedEvent
from backend.gridiron.services import backup as backup_service
from backend.gridiron.services import (
    differ,
    events,
    fantasy_service,
    live_state,
    live_tier,
    quiescence,
)

logger = logging.getLogger("uvicorn.error")

_scheduler: AsyncIOScheduler | None = None

# Adaptive-cadence intervals (task 8.3) for `refresh_fantasy` when live_state isn't
# "live" (the "live" case reads the configured tier from `services/live_tier.py`
# instead).
GAME_DAY_INTERVAL_SECONDS = 5 * 60
OFF_DAY_INTERVAL_SECONDS = 30 * 60

# `refresh_nfl_state` poll cadence (task 8.2) — the in-season default; both this and
# `refresh_fantasy` back off further during the off-season (task 11.7, services/quiescence.py).
NFL_STATE_INTERVAL_SECONDS = 30

# `refresh_player_pool` cadence — fixed, never rescheduled from live_state
# (add-player-pool design D8).
#
# Deliberately a few minutes LONGER than the client's `PLAYER_POOL_TTL` (6h). If the
# two were equal, a tick arriving a moment early — scheduler jitter, a slow previous
# run — would find its own cache entry still fresh, skip every league, and leave the
# pool unrefreshed for another full interval. The margin makes expiry always precede
# the next tick.
PLAYER_POOL_INTERVAL_SECONDS = 6 * 60 * 60 + 5 * 60

# `refresh_injuries` cadence — fixed, and deliberately NOT bound to the live tier.
# Injury reports are filed on practice-report and gameday-inactive schedules (a handful of
# times a week), not on a snap-by-snap one, so tying this to the 10s live tier would issue
# ~130 requests against a free public endpoint every ten seconds to re-read prose that
# changes on Wednesdays.
INJURIES_INTERVAL_SECONDS = 30 * 60


class UnknownJobError(GridironError):
    """Raised when a job name isn't in the `JOBS` registry."""


async def _sync_discovery(session: AsyncSession) -> str | None:
    """League/team discovery + credential probe. Returns an error summary string when any
    platform failed (recorded on the run), else `None`."""
    outcomes = await fantasy_service.refresh_discovery(session)
    return fantasy_service.summarize_outcomes(outcomes)


async def _is_off_season(session: AsyncSession) -> bool:
    now = datetime.now(UTC).replace(tzinfo=None)
    newest_kickoff = await quiescence.get_newest_kickoff_seen(session)
    return quiescence.is_off_season(now, newest_kickoff)


async def _refresh_fantasy_interval_seconds(session: AsyncSession) -> int:
    """The interval `refresh_fantasy` should run at *right now*, from the current
    live_state (+ the configured live tier, when live). Off-season (task 11.7) only
    ever kicks in on top of the "off_day" branch — a `live`/`game_day` verdict always
    means something real is happening regardless of how stale the quiescence watermark
    looks, so it always wins."""
    state = live_state.get_current_live_state()
    if state == "live":
        tier = await live_tier.get_live_tier(session)
        return live_tier.tier_seconds(tier)
    if state == "game_day":
        return GAME_DAY_INTERVAL_SECONDS
    if await _is_off_season(session):
        return quiescence.OFF_SEASON_FANTASY_INTERVAL_SECONDS
    return OFF_DAY_INTERVAL_SECONDS


async def _refresh_nfl_state_interval_seconds(session: AsyncSession) -> int:
    """The interval `refresh_nfl_state` should poll at *right now* (task 11.7) — the
    normal 30s cadence, or hourly once quiescent."""
    if await _is_off_season(session):
        return quiescence.OFF_SEASON_NFL_STATE_INTERVAL_SECONDS
    return NFL_STATE_INTERVAL_SECONDS


async def reschedule_refresh_fantasy(session: AsyncSession) -> None:
    """Reschedule the running `refresh_fantasy` job from the current live_state/tier.

    Called after every `refresh_fantasy` run (self-rescheduling adaptive cadence, task
    8.3) and immediately from `POST /api/settings/live-tier` so an in-progress live
    session picks up a tier change without waiting for the next tick. A no-op when the
    scheduler isn't running (dev default, `GRIDIRON_SCHEDULER_ENABLED=false`) or the job
    isn't registered — jobs stay directly invokable via `run_job` either way.
    """
    if _scheduler is None or _scheduler.get_job("refresh_fantasy") is None:
        return
    seconds = await _refresh_fantasy_interval_seconds(session)
    _scheduler.reschedule_job("refresh_fantasy", trigger=IntervalTrigger(seconds=seconds))


async def reschedule_refresh_nfl_state(session: AsyncSession) -> None:
    """Reschedule the running `refresh_nfl_state` job from the current quiescence state
    (task 11.7) — same no-op-when-not-running shape as `reschedule_refresh_fantasy`."""
    if _scheduler is None or _scheduler.get_job("refresh_nfl_state") is None:
        return
    seconds = await _refresh_nfl_state_interval_seconds(session)
    _scheduler.reschedule_job("refresh_nfl_state", trigger=IntervalTrigger(seconds=seconds))


async def _refresh_fantasy(session: AsyncSession) -> str | None:
    """The actual fetch+diff+publish work lives in `fantasy_service.refresh_fantasy`;
    this wrapper's only extra job is the self-rescheduling side effect, which needs
    `_scheduler` — a module `fantasy_service` intentionally doesn't know about
    (layering, not laziness: services stay ignorant of the scheduler that calls them)."""
    error = await fantasy_service.refresh_fantasy(session)
    await reschedule_refresh_fantasy(session)
    return error


async def _refresh_nfl_state(session: AsyncSession) -> str | None:
    """Poll ESPN's public scoreboard, upsert `live_nfl_games`, reclassify live_state, and
    publish `live_state.changed` on a transition + `data.changed` for the
    `"live_nfl_games"` scope when anything actually moved (task 8.2). Also feeds the
    off-season quiescence watermark and self-reschedules from it (task 11.7) — same
    "wrapper owns the scheduler side effect" split as `_refresh_fantasy`."""
    games = await nfl_scoreboard.fetch_and_upsert(session)
    await quiescence.record_kickoffs_seen(session, games)

    teams = await live_state.user_nfl_teams(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    new_state = live_state.classify(games, teams, now)
    if new_state != live_state.get_current_live_state():
        live_state.set_current_live_state(new_state)
        events.publish(LiveStateChangedEvent(live_state=new_state))

    fingerprints = await differ.live_nfl_games_fingerprints(session)
    differ.diff_and_publish(fingerprints)
    await reschedule_refresh_nfl_state(session)
    return None


async def _refresh_player_pool(session: AsyncSession) -> str | None:
    """Free-agent/waiver/rostered pool + season projections, per league.

    No self-rescheduling counterpart to `_refresh_fantasy`'s: this job's cadence is
    fixed by design (D8). It fans out across every league at ~3.7 MB each, so binding
    it to the live tier would issue that fan-out up to 120x an hour during games — for
    data that only moves when waiver claims process.
    """
    return await fantasy_service.refresh_player_pool(session)


async def _refresh_injuries(session: AsyncSession) -> str | None:
    """ESPN injury-report detail for players the fantasy API already flags as non-healthy
    (add-player-health D2/D3). The only writer of `player_injuries` — `GET /api/players/
    {id}/injury` serves whatever this leaves behind and never fetches (design.md D7)."""
    return await espn_injuries.fetch_and_upsert(session)


async def _backup_db(session: AsyncSession) -> str | None:
    """Nightly SQLite backup + prune (task 11.4). Doesn't touch `session` — the backup
    runs against the on-disk file directly via `sqlite3`'s own online-backup API — but
    still takes one to match the `JOBS` protocol every other job follows."""
    del session
    await backup_service.run_backup(resolve_db_path())
    return None


# Job registry: name -> coroutine taking a session and returning an optional error
# summary (recorded on the `refresh_runs` row `run_job` writes).
JOBS: dict[str, Callable[[AsyncSession], Awaitable[str | None]]] = {
    "sync_discovery": _sync_discovery,
    "refresh_fantasy": _refresh_fantasy,
    "refresh_nfl_state": _refresh_nfl_state,
    "refresh_player_pool": _refresh_player_pool,
    "refresh_injuries": _refresh_injuries,
    "backup_db": _backup_db,
}


async def run_job(job_name: str, session: AsyncSession) -> RefreshRun:
    """Run `job_name` immediately on `session` and record a `refresh_runs` row.

    This is the single execution path for both scheduled runs and the manual
    `POST /api/admin/refresh` trigger — the latter works even when the scheduler is
    disabled, because this calls the underlying coroutine directly.
    """
    try:
        job = JOBS[job_name]
    except KeyError as exc:
        raise UnknownJobError(f"unknown job: {job_name!r}") from exc

    run_at = datetime.now(UTC).replace(tzinfo=None)
    started = time.monotonic()
    try:
        error = await job(session)
        ok = error is None
    except Exception as exc:  # record the failure; never let a job kill the scheduler
        logger.exception("job %s failed", job_name)
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    duration_ms = int((time.monotonic() - started) * 1000)

    run = RefreshRun(job_name=job_name, run_at=run_at, ok=ok, error=error, duration_ms=duration_ms)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # Task 11.2/11.3: exactly one summary line per run — WARN on failure (so it's
    # visible without DEBUG-level noise), INFO on success.
    log = logger.info if ok else logger.warning
    log("job=%s duration_ms=%d ok=%s error=%s", job_name, duration_ms, ok, error)
    return run


async def _scheduled(job_name: str) -> None:
    """Scheduler entrypoint: give each run its own session from the app-wide factory."""
    async with async_session_factory() as session:
        await run_job(job_name, session)


def start_scheduler() -> AsyncIOScheduler:
    """Create + start the AsyncIOScheduler (called from FastAPI's lifespan when
    `GRIDIRON_SCHEDULER_ENABLED` is true). Must run inside a running event loop."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _scheduled,
        CronTrigger(hour=6, minute=0),  # daily 06:00 local (design.md D8)
        args=["sync_discovery"],
        id="sync_discovery",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled,
        # Safe initial default (off-day cadence) — `refresh_fantasy` reschedules itself
        # from the real live_state after its very first run (task 8.3), and
        # `refresh_nfl_state`'s own 30s ticks keep live_state current in the meantime.
        IntervalTrigger(seconds=OFF_DAY_INTERVAL_SECONDS),
        args=["refresh_fantasy"],
        id="refresh_fantasy",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled,
        # Safe initial default (in-season cadence) — `refresh_nfl_state` reschedules
        # itself from the real quiescence state after its very first run (task 11.7).
        IntervalTrigger(seconds=NFL_STATE_INTERVAL_SECONDS),
        args=["refresh_nfl_state"],
        id="refresh_nfl_state",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled,
        # Fixed cadence, deliberately NOT adaptive (add-player-pool design D8): the job
        # pulls ~3.7 MB per league across every league, and the pool only changes when
        # waiver claims process.
        IntervalTrigger(seconds=PLAYER_POOL_INTERVAL_SECONDS),
        args=["refresh_player_pool"],
        id="refresh_player_pool",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled,
        # Fixed cadence for the same reason as `refresh_player_pool`: the data behind it
        # moves on a weekly practice-report rhythm, not a live one.
        IntervalTrigger(seconds=INJURIES_INTERVAL_SECONDS),
        args=["refresh_injuries"],
        id="refresh_injuries",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled,
        CronTrigger(hour=3, minute=0),  # nightly ~03:00 local (task 11.4)
        args=["backup_db"],
        id="backup_db",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler started (jobs: %s)", ", ".join(sorted(JOBS)))
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")


def next_run_time() -> datetime | None:
    """Earliest next planned run across registered jobs, or `None` when the scheduler
    isn't running (dev default). Feeds `meta.next_refresh_at`."""
    if _scheduler is None:
        return None
    times = [job.next_run_time for job in _scheduler.get_jobs() if job.next_run_time]
    return min(times, default=None)
