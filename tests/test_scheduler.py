"""`scheduler.py` — the Phase 8 adaptive-cadence jobs (task 8.3): job registration,
interval selection from live_state/tier, and the self-/settings-triggered reschedule
(exercised without a running `AsyncIOScheduler` — jobs stay invokable via `run_job` per
the "scheduler off by default in dev" rule)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron import scheduler
from backend.gridiron.db import make_engine
from backend.gridiron.models import AppSetting, Base, RefreshRun
from backend.gridiron.services import (
    differ,
    events,
    fantasy_service,
    live_state,
    live_tier,
    quiescence,
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    live_state.reset_state()
    differ.reset_state()
    events.reset()
    yield
    fantasy_service.reset_state()
    live_state.reset_state()
    differ.reset_state()
    events.reset()


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "scheduler.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def test_jobs_registry_includes_the_phase_8_jobs() -> None:
    assert set(scheduler.JOBS) == {
        "sync_discovery",
        "refresh_fantasy",
        "refresh_nfl_state",
        "refresh_player_pool",
        "backup_db",
    }


@pytest.mark.asyncio
async def test_refresh_fantasy_runs_and_is_recorded_without_a_running_scheduler(
    session_factory,
) -> None:
    async with session_factory() as session:
        run = await scheduler.run_job("refresh_fantasy", session)

    assert run.job_name == "refresh_fantasy"
    assert run.ok is True

    async with session_factory() as session:
        rows = (await session.execute(select(RefreshRun))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_refresh_nfl_state_runs_via_run_job(session_factory, monkeypatch) -> None:
    async def fake_fetch_and_upsert(session):
        return []

    monkeypatch.setattr(
        "backend.gridiron.platforms.nfl_scoreboard.fetch_and_upsert", fake_fetch_and_upsert
    )

    async with session_factory() as session:
        run = await scheduler.run_job("refresh_nfl_state", session)

    assert run.job_name == "refresh_nfl_state"
    assert run.ok is True
    # No games -> classify() returns "off_day", the module default, so no transition.
    assert live_state.get_current_live_state() == "off_day"


@pytest.mark.asyncio
async def test_refresh_nfl_state_publishes_live_state_changed_on_transition(
    session_factory, monkeypatch
) -> None:
    from backend.gridiron.schemas.live_nfl_games import LiveNflGame

    async def fake_fetch_and_upsert(session):
        return [
            LiveNflGame(
                nfl_game_id="1",
                home_team="KC",
                away_team="BUF",
                home_score=7,
                away_score=0,
                state="in",
                clock="10:00",
                period=1,
                kickoff_at=datetime.now(UTC).replace(tzinfo=None),
            )
        ]

    async def fake_user_nfl_teams(session):
        return {"KC"}

    monkeypatch.setattr(
        "backend.gridiron.platforms.nfl_scoreboard.fetch_and_upsert", fake_fetch_and_upsert
    )
    monkeypatch.setattr(live_state, "user_nfl_teams", fake_user_nfl_teams)

    queue = events.subscribe()

    async with session_factory() as session:
        await scheduler.run_job("refresh_nfl_state", session)

    assert live_state.get_current_live_state() == "live"
    published = [queue.get_nowait() for _ in range(queue.qsize())]
    assert any(getattr(e, "live_state", None) == "live" for e in published)


@pytest.mark.asyncio
async def test_reschedule_refresh_fantasy_is_a_no_op_without_a_running_scheduler(
    session_factory,
) -> None:
    async with session_factory() as session:
        await scheduler.reschedule_refresh_fantasy(session)  # must not raise


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_off_day_default(session_factory) -> None:
    live_state.set_current_live_state("off_day")
    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == scheduler.OFF_DAY_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_game_day(session_factory) -> None:
    live_state.set_current_live_state("game_day")
    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == scheduler.GAME_DAY_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_live_reads_configured_tier(session_factory) -> None:
    live_state.set_current_live_state("live")
    async with session_factory() as session:
        session.add(AppSetting(key="live_tier", value="10s"))
        await session.commit()

    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == 10


# --- task 11.7: off-season quiescence wiring ------------------------------------------


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_off_day_and_quiescent_backs_off(
    session_factory,
) -> None:
    live_state.set_current_live_state("off_day")
    async with session_factory() as session:
        session.add(
            AppSetting(
                key=quiescence.NEWEST_KICKOFF_KEY,
                value=(datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat(),
            )
        )
        await session.commit()

    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == quiescence.OFF_SEASON_FANTASY_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_live_state_wins_over_quiescence(
    session_factory,
) -> None:
    """A stale quiescence watermark never overrides an actual live/game_day verdict --
    e.g. the app was off for months and the very first tick back sees a live game before
    `record_kickoffs_seen` has had a chance to refresh the watermark."""
    live_state.set_current_live_state("live")
    async with session_factory() as session:
        session.add(
            AppSetting(
                key=quiescence.NEWEST_KICKOFF_KEY,
                value=(datetime.now(UTC).replace(tzinfo=None) - timedelta(days=200)).isoformat(),
            )
        )
        await session.commit()

    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == live_tier.tier_seconds(live_tier.DEFAULT_LIVE_TIER)


@pytest.mark.asyncio
async def test_refresh_nfl_state_interval_seconds_defaults_to_thirty_seconds(
    session_factory,
) -> None:
    async with session_factory() as session:
        seconds = await scheduler._refresh_nfl_state_interval_seconds(session)
    assert seconds == scheduler.NFL_STATE_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_refresh_nfl_state_interval_seconds_backs_off_when_quiescent(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            AppSetting(
                key=quiescence.NEWEST_KICKOFF_KEY,
                value=(datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat(),
            )
        )
        await session.commit()

    async with session_factory() as session:
        seconds = await scheduler._refresh_nfl_state_interval_seconds(session)
    assert seconds == quiescence.OFF_SEASON_NFL_STATE_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_refresh_nfl_state_records_kickoffs_seen(session_factory, monkeypatch) -> None:
    from backend.gridiron.schemas.live_nfl_games import LiveNflGame

    kickoff = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)

    async def fake_fetch_and_upsert(session):
        return [
            LiveNflGame(
                nfl_game_id="1",
                home_team="KC",
                away_team="BUF",
                home_score=0,
                away_score=0,
                state="pre",
                clock=None,
                period=None,
                kickoff_at=kickoff,
            )
        ]

    monkeypatch.setattr(
        "backend.gridiron.platforms.nfl_scoreboard.fetch_and_upsert", fake_fetch_and_upsert
    )

    async with session_factory() as session:
        await scheduler.run_job("refresh_nfl_state", session)

    async with session_factory() as session:
        newest = await quiescence.get_newest_kickoff_seen(session)
    assert newest == kickoff


@pytest.mark.asyncio
async def test_reschedule_refresh_nfl_state_is_a_no_op_without_a_running_scheduler(
    session_factory,
) -> None:
    async with session_factory() as session:
        await scheduler.reschedule_refresh_nfl_state(session)  # must not raise


@pytest.mark.asyncio
async def test_reschedule_refresh_nfl_state_updates_the_running_job_interval(
    session_factory,
) -> None:
    running = scheduler.start_scheduler()
    try:
        async with session_factory() as session:
            session.add(
                AppSetting(
                    key=quiescence.NEWEST_KICKOFF_KEY,
                    value=(datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat(),
                )
            )
            await session.commit()
            await scheduler.reschedule_refresh_nfl_state(session)

        job = running.get_job("refresh_nfl_state")
        assert (
            job.trigger.interval.total_seconds() == quiescence.OFF_SEASON_NFL_STATE_INTERVAL_SECONDS
        )
    finally:
        scheduler.shutdown_scheduler()


# --- task 11.4: nightly backup job ------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_db_job_runs_via_run_job(session_factory, tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "gridiron.db"
    db_path.write_bytes(b"")  # sqlite3.connect will initialize it as a valid empty DB
    monkeypatch.setattr(scheduler, "resolve_db_path", lambda: db_path)

    async with session_factory() as session:
        run = await scheduler.run_job("backup_db", session)

    assert run.job_name == "backup_db"
    assert run.ok is True
    assert (db_path.parent / "backups" / f"gridiron-{datetime.now(UTC):%Y%m%d}.db").exists()


# --- task 11.2: a failed run must never publish data.changed ---------------------------


@pytest.mark.asyncio
async def test_run_job_failure_does_not_publish_data_changed(session_factory, monkeypatch) -> None:
    queue = events.subscribe()

    async def boom(session):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(scheduler.JOBS, "refresh_fantasy", boom)

    async with session_factory() as session:
        run = await scheduler.run_job("refresh_fantasy", session)

    assert run.ok is False
    assert queue.empty()


@pytest.mark.asyncio
async def test_refresh_fantasy_interval_seconds_live_defaults_to_30s(session_factory) -> None:
    live_state.set_current_live_state("live")
    async with session_factory() as session:
        seconds = await scheduler._refresh_fantasy_interval_seconds(session)
    assert seconds == 30


@pytest.mark.asyncio
async def test_start_scheduler_registers_every_job_then_shuts_down() -> None:
    running = scheduler.start_scheduler()
    try:
        job_ids = {job.id for job in running.get_jobs()}
        assert job_ids == {
            "sync_discovery",
            "refresh_fantasy",
            "refresh_nfl_state",
            "refresh_player_pool",
            "backup_db",
        }
    finally:
        scheduler.shutdown_scheduler()


@pytest.mark.asyncio
async def test_reschedule_refresh_fantasy_updates_the_running_job_interval(session_factory) -> None:
    running = scheduler.start_scheduler()
    try:
        live_state.set_current_live_state("live")
        async with session_factory() as session:
            session.add(AppSetting(key="live_tier", value="10s"))
            await session.commit()
            await scheduler.reschedule_refresh_fantasy(session)

        job = running.get_job("refresh_fantasy")
        assert job.trigger.interval.total_seconds() == 10
    finally:
        scheduler.shutdown_scheduler()


# ---------------------------------------------------------------------------
# refresh_player_pool (add-player-pool group 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_player_pool_runs_via_run_job(session_factory) -> None:
    """No ESPN connection persisted, so the job is a well-behaved no-op: it records a
    successful run rather than erroring, matching how the other jobs treat a
    disconnected platform."""
    async with session_factory() as session:
        run = await scheduler.run_job("refresh_player_pool", session)

        assert run.ok is True
        assert run.error is None
        rows = (await session.execute(select(RefreshRun))).scalars().all()
        assert [r.job_name for r in rows] == ["refresh_player_pool"]


@pytest.mark.asyncio
async def test_player_pool_cadence_outlasts_its_cache_ttl() -> None:
    """The interval must exceed `PLAYER_POOL_TTL`, not equal it.

    If they matched, a tick arriving a moment early (scheduler jitter, a slow previous
    run) would find its own cache entry still fresh, skip every league, and leave the
    pool stale for another full interval.
    """
    from backend.gridiron.platforms.espn.client import PLAYER_POOL_TTL

    assert scheduler.PLAYER_POOL_INTERVAL_SECONDS > PLAYER_POOL_TTL.total_seconds()


@pytest.mark.asyncio
async def test_player_pool_interval_is_fixed_not_live_adaptive(session_factory) -> None:
    """Design D8: the pool job fans out ~3.7 MB per league, so it must never inherit
    `refresh_fantasy`'s live-tier cadence — that would issue the fan-out up to 120x an
    hour during games."""
    running = scheduler.start_scheduler()
    try:
        before = running.get_job("refresh_player_pool").trigger.interval.total_seconds()

        live_state.set_current_live_state("live")
        async with session_factory() as session:
            await scheduler.reschedule_refresh_fantasy(session)

        after = running.get_job("refresh_player_pool").trigger.interval.total_seconds()
        fantasy = running.get_job("refresh_fantasy").trigger.interval.total_seconds()

        assert after == before == scheduler.PLAYER_POOL_INTERVAL_SECONDS
        assert fantasy < after, "sanity: the fantasy job did drop to a live cadence"
    finally:
        scheduler.shutdown_scheduler()
