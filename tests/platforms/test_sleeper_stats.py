"""Sleeper stats ingest — row filtering, the backfill/tail policy, live ticks, and the
`sleeper_id` bridge (add-player-stats)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, PlayerStatSeason, PlayerWeeklyStat
from backend.gridiron.platforms import sleeper, sleeper_stats

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "sleeper" / "stats_week_2025_10.json").read_text()
)
FETCHED_AT = datetime(2026, 10, 22, 12, 0, 0)


class FakeStatsClient:
    def __init__(self, weeks: dict[tuple[int, int], list[dict]] | None = None, fail=False):
        self.weeks = weeks or {}
        self.fail = fail
        self.calls: list[tuple[int, int]] = []

    async def get_week(self, season, week):
        self.calls.append((season, week))
        if self.fail:
            raise httpx.ConnectError("boom")
        return self.weeks.get((season, week), [])

    async def aclose(self):  # pragma: no cover - never owned by the code under test
        pass


class FakePlayersClient:
    def __init__(self, dump=None):
        self.dump = dump or {}

    async def get_players(self, session):
        return self.dump

    async def aclose(self):  # pragma: no cover
        pass


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "sleeper-stats.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_league(db, season=2026, week=7):
    async with db() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=season,
                team_count=10,
                scoring_type="ppr",
                current_week=week,
            )
        )
        await session.commit()


# ---- map_row --------------------------------------------------------------------------


def test_map_row_keeps_games_played_and_trims_stats():
    rows = [sleeper_stats.map_row(r, season=2025, week=10, fetched_at=FETCHED_AT) for r in FIXTURE]
    kept = [r for r in rows if r is not None]
    # Murtagh was active with no `gp` — not a game in a game log.
    assert {r["sleeper_id"] for r in kept} == {"DEN", "4034", "1373", "3678"}

    cmc = next(r for r in kept if r["sleeper_id"] == "4034")
    assert (cmc["team"], cmc["opponent"], cmc["game_date"]) == ("SF", "LAR", "2025-11-09")
    assert (cmc["pts_ppr"], cmc["pts_half_ppr"], cmc["pts_std"]) == (17.6, 13.6, 9.6)
    stats = json.loads(cmc["stats_json"])
    assert stats["rec"] == 8.0
    assert set(stats) <= sleeper_stats.KEPT_STATS
    assert "pos_rank_ppr" not in stats and "tm_def_snp" not in stats


# ---- policy ---------------------------------------------------------------------------


def state(complete=False, through=0, fetched_at=FETCHED_AT):
    return PlayerStatSeason(
        season=0, complete=complete, fetched_through_week=through, fetched_at=fetched_at
    )


def test_weeks_to_fetch_past_season_once():
    assert sleeper_stats.weeks_to_fetch(2024, 2026, 7, None) == list(range(1, 19))
    assert sleeper_stats.weeks_to_fetch(2024, 2026, 7, state(complete=True)) == []


def test_weeks_to_fetch_current_season_fills_gaps_and_refetches_tail():
    assert sleeper_stats.weeks_to_fetch(2026, 2026, 7, None) == list(range(1, 8))
    # Already through week 7: only the in-progress week and the one taking corrections.
    assert sleeper_stats.weeks_to_fetch(2026, 2026, 7, state(through=7)) == [6, 7]
    assert sleeper_stats.weeks_to_fetch(2026, 2026, 9, state(through=7)) == [8, 9]
    assert sleeper_stats.weeks_to_fetch(2026, 2026, 1, state(through=1)) == [1]


def test_is_full_pass_due():
    assert sleeper_stats.is_full_pass_due(None, FETCHED_AT)
    recent = state(fetched_at=FETCHED_AT - timedelta(minutes=5))
    assert not sleeper_stats.is_full_pass_due(recent, FETCHED_AT)
    stale = state(fetched_at=FETCHED_AT - sleeper_stats.FULL_INTERVAL)
    assert sleeper_stats.is_full_pass_due(stale, FETCHED_AT)


# ---- fetch_and_upsert -----------------------------------------------------------------


async def test_backfill_marks_past_seasons_complete(db, monkeypatch):
    monkeypatch.setattr(sleeper_stats, "HISTORY_SEASONS", 2)
    await seed_league(db, season=2026, week=2)
    client = FakeStatsClient({(2025, 10): FIXTURE})

    async with db() as session:
        error = await sleeper_stats.fetch_and_upsert(session, client, FakePlayersClient())
    assert error is None
    assert client.calls == [(2025, w) for w in range(1, 19)] + [(2026, 1), (2026, 2)]

    async with db() as session:
        states = {s.season: s for s in (await session.execute(select(PlayerStatSeason))).scalars()}
        assert states[2025].complete and states[2025].fetched_through_week == 18
        assert not states[2026].complete and states[2026].fetched_through_week == 2
        rows = (await session.execute(select(PlayerWeeklyStat))).scalars().all()
        assert len(rows) == 4

    # A second full pass never asks for 2025 again.
    async with db() as session:
        states_rows = (await session.execute(select(PlayerStatSeason))).scalars().all()
        for s in states_rows:
            s.fetched_at = FETCHED_AT - timedelta(days=1)
        await session.commit()
    client.calls.clear()
    async with db() as session:
        await sleeper_stats.fetch_and_upsert(session, client, FakePlayersClient())
    assert client.calls == [(2026, 1), (2026, 2)]


async def test_upsert_overwrites_corrected_week(db, monkeypatch):
    monkeypatch.setattr(sleeper_stats, "HISTORY_SEASONS", 1)
    await seed_league(db, season=2025, week=10)
    async with db() as session:
        await sleeper_stats.fetch_and_upsert(
            session, FakeStatsClient({(2025, 10): FIXTURE}), FakePlayersClient()
        )

    corrected = json.loads(json.dumps(FIXTURE))
    for row in corrected:
        if row["player_id"] == "4034":
            row["stats"]["pts_ppr"] = 20.0
    async with db() as session:
        for s in (await session.execute(select(PlayerStatSeason))).scalars():
            s.fetched_at = FETCHED_AT - timedelta(days=1)
        await session.commit()
        await sleeper_stats.fetch_and_upsert(
            session, FakeStatsClient({(2025, 10): corrected}), FakePlayersClient()
        )
        row = await session.get(PlayerWeeklyStat, ("4034", 2025, 10))
        assert row.pts_ppr == 20.0


async def test_live_tick_fetches_only_current_week(db):
    await seed_league(db, season=2026, week=7)
    async with db() as session:
        session.add(
            PlayerStatSeason(
                season=2026,
                complete=False,
                fetched_through_week=7,
                fetched_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()

    quiet = FakeStatsClient()
    async with db() as session:
        assert await sleeper_stats.fetch_and_upsert(session, quiet, FakePlayersClient()) is None
    assert quiet.calls == []

    live = FakeStatsClient()
    async with db() as session:
        await sleeper_stats.fetch_and_upsert(session, live, FakePlayersClient(), live=True)
    assert live.calls == [(2026, 7)]


async def test_http_error_is_reported_not_raised(db, monkeypatch):
    monkeypatch.setattr(sleeper_stats, "HISTORY_SEASONS", 1)
    await seed_league(db)
    async with db() as session:
        error = await sleeper_stats.fetch_and_upsert(
            session, FakeStatsClient(fail=True), FakePlayersClient()
        )
    assert error is not None and error.startswith("sleeper stats unavailable")


# ---- bridge_sleeper_ids ---------------------------------------------------------------

DUMP = {
    "4034": {
        "espn_id": 3117251,
        "yahoo_id": 30121,
        "first_name": "Christian",
        "last_name": "McCaffrey",
        "team": "SF",
        "position": "RB",
    },
    "222": {"espn_id": None, "first_name": "Travis", "last_name": "Etienne", "team": "JAX"},
    # Two same-name players on one team — dropped, never guessed.
    "301": {"first_name": "Josh", "last_name": "Allen", "team": "BUF", "position": "QB"},
    "302": {"first_name": "Josh", "last_name": "Allen", "team": "BUF", "position": "LB"},
    "SF": {"first_name": "San Francisco", "last_name": "49ers", "position": "DEF", "team": "SF"},
}


def player(pid, name, team, position="RB"):
    platform, platform_id = pid.split(":", 1)
    return Player(
        id=pid,
        platform=platform,
        platform_id=platform_id,
        name=name,
        position=position,
        nfl_team=team,
    )


def test_bridge_sleeper_ids_tiers():
    players = [
        player("espn:p-3117251", "Christian McCaffrey", "SF"),
        player("yahoo:470.p.30121", "Christian McCaffrey", "SF"),
        player("espn:p-999", "Travis Etienne Jr.", "JAX"),
        player("espn:p--16025", "49ers D/ST", "SF", "DST"),
        player("espn:p-1", "Josh Allen", "BUF", "QB"),
        player("espn:p-2", "Nobody", "FA"),
    ]
    assert sleeper.bridge_sleeper_ids(DUMP, players) == 4
    assert [p.sleeper_id for p in players] == ["4034", "4034", "222", "SF", None, None]
    # Idempotent: a second pass changes nothing.
    assert sleeper.bridge_sleeper_ids(DUMP, players) == 0
