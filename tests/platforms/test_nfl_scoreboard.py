"""`platforms/nfl_scoreboard.py` — the public ESPN scoreboard client/mapper/upsert
(task 8.2), against a synthetic captured-shape fixture."""

import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, LiveNflGame as LiveNflGameRow
from backend.gridiron.platforms import nfl_scoreboard

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_scoreboard() -> dict:
    return json.loads((FIXTURES / "nfl" / "scoreboard.json").read_text())


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "nfl-scoreboard.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


# --- map_scoreboard -----------------------------------------------------------------


class TestMapScoreboard:
    def test_maps_in_progress_game(self) -> None:
        games = nfl_scoreboard.map_scoreboard(load_scoreboard())
        live = next(g for g in games if g.nfl_game_id == "401547439")

        assert live.home_team == "KC"
        assert live.away_team == "BUF"
        assert live.home_score == 27
        assert live.away_score == 24
        assert live.state == "in"
        assert live.clock == "2:05"
        assert live.period == 4
        assert live.kickoff_at == datetime(2025, 12, 7, 18, 0)

    def test_maps_pregame_game_with_no_clock_or_period(self) -> None:
        games = nfl_scoreboard.map_scoreboard(load_scoreboard())
        pregame = next(g for g in games if g.nfl_game_id == "401547440")

        assert pregame.state == "pre"
        assert pregame.clock is None
        assert pregame.period is None
        assert pregame.home_score == 0
        assert pregame.away_score == 0

    def test_maps_final_game(self) -> None:
        games = nfl_scoreboard.map_scoreboard(load_scoreboard())
        final = next(g for g in games if g.nfl_game_id == "401547438")

        assert final.state == "post"
        assert final.home_team == "MIA"
        assert final.away_team == "NYJ"
        assert final.home_score == 31
        assert final.away_score == 17

    def test_maps_every_event(self) -> None:
        games = nfl_scoreboard.map_scoreboard(load_scoreboard())
        assert len(games) == 3

    def test_skips_malformed_event_without_failing_the_whole_poll(self) -> None:
        payload = {
            "events": [
                {"id": "bad", "competitions": []},  # missing competitors -> IndexError
                *load_scoreboard()["events"],
            ]
        }
        games = nfl_scoreboard.map_scoreboard(payload)
        assert len(games) == 3
        assert all(g.nfl_game_id != "bad" for g in games)

    def test_postponed_status_name_maps_to_postponed_state(self) -> None:
        payload = {
            "events": [
                {
                    "id": "999",
                    "date": "2025-12-07T18:00Z",
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"abbreviation": "KC"}, "score": "0"},
                                {"homeAway": "away", "team": {"abbreviation": "BUF"}, "score": "0"},
                            ],
                            "status": {
                                "displayClock": "0:00",
                                "period": 0,
                                "type": {"name": "STATUS_POSTPONED", "state": "post"},
                            },
                        }
                    ],
                }
            ]
        }
        games = nfl_scoreboard.map_scoreboard(payload)
        assert games[0].state == "postponed"


# --- upsert_games / fetch_and_upsert -------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_games_writes_rows(session_factory) -> None:
    games = nfl_scoreboard.map_scoreboard(load_scoreboard())

    async with session_factory() as session:
        await nfl_scoreboard.upsert_games(session, games)

    async with session_factory() as session:
        rows = (await session.execute(select(LiveNflGameRow))).scalars().all()
    assert len(rows) == 3
    assert {r.nfl_game_id for r in rows} == {"401547439", "401547440", "401547438"}


@pytest.mark.asyncio
async def test_upsert_games_updates_existing_row_on_rerun(session_factory) -> None:
    games = nfl_scoreboard.map_scoreboard(load_scoreboard())
    async with session_factory() as session:
        await nfl_scoreboard.upsert_games(session, games)

    updated = [g.model_copy(update={"home_score": 34}) for g in games]
    async with session_factory() as session:
        await nfl_scoreboard.upsert_games(session, updated)

    async with session_factory() as session:
        rows = (await session.execute(select(LiveNflGameRow))).scalars().all()
    assert len(rows) == 3  # still one row per game, not duplicated
    live_row = next(r for r in rows if r.nfl_game_id == "401547439")
    assert live_row.home_score == 34


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_upsert_hits_the_public_scoreboard_url(session_factory) -> None:
    respx.get(nfl_scoreboard.SCOREBOARD_URL).mock(
        return_value=httpx.Response(200, json=load_scoreboard())
    )

    async with session_factory() as session:
        games = await nfl_scoreboard.fetch_and_upsert(session)

    assert len(games) == 3
    async with session_factory() as session:
        rows = (await session.execute(select(LiveNflGameRow))).scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
@respx.mock
async def test_get_scoreboard_raises_on_http_error(session_factory) -> None:
    respx.get(nfl_scoreboard.SCOREBOARD_URL).mock(return_value=httpx.Response(503))

    client = nfl_scoreboard.NflScoreboardClient()
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_scoreboard()
    await client.aclose()
