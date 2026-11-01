"""`services/nfl_week_cache.py` — trimming and caching NFL weeks for the Scores screen
(add-nfl-scores), against payloads captured from ESPN and Sleeper."""

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base
from backend.gridiron.services import nfl_week_cache

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_week() -> dict:
    return json.loads((FIXTURES / "nfl" / "scores_week.json").read_text())


def load_projection_rows() -> list[dict]:
    return json.loads((FIXTURES / "sleeper" / "week_projections.json").read_text())["rows"]


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "nfl-week-cache.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _event(trimmed: dict, game_id: str) -> dict:
    return next(e for e in trimmed["events"] if e["id"] == game_id)


class TestNormalizeTeam:
    def test_espn_washington_becomes_the_apps_abbreviation(self) -> None:
        assert nfl_week_cache.normalize_team("WSH") == "WAS"

    def test_everything_else_passes_through_uppercased(self) -> None:
        assert nfl_week_cache.normalize_team("cin") == "CIN"
        assert nfl_week_cache.normalize_team(None) == ""


class TestTrimScoreboard:
    def test_keeps_the_season_week_and_normalized_byes(self) -> None:
        trimmed = nfl_week_cache.trim_scoreboard(load_week())

        assert trimmed is not None
        assert (trimmed["season"], trimmed["week"]) == (2025, 7)
        assert trimmed["byes"] == ["BAL", "BUF"]
        assert len(trimmed["events"]) == 4

    def test_final_game_carries_records_linescores_logo_and_winner(self) -> None:
        final = _event(nfl_week_cache.trim_scoreboard(load_week()), "401772941")

        assert final["state"] == "post"
        assert final["home"]["abbr"] == "CIN"
        assert final["home"]["name"] == "Bengals"
        assert final["home"]["score"] == 33
        assert final["home"]["winner"] is True
        assert final["away"]["winner"] is False
        assert final["home"]["linescores"][:2] == [0, 17]
        assert final["home"]["record"]
        assert final["home"]["logo"].startswith("https://")
        assert final["broadcast"] == "Prime Video"

    def test_leaders_keep_athlete_and_team(self) -> None:
        final = _event(nfl_week_cache.trim_scoreboard(load_week()), "401772941")
        passing = next(leader for leader in final["leaders"] if leader["category"] == "passing")

        assert passing["name"] == "Joe Flacco"
        assert passing["short_name"] == "J. Flacco"
        assert passing["athlete_id"] == "11252"
        assert passing["team"] == "CIN"
        assert passing["display_value"].startswith("31/47")

    def test_washington_is_normalized_inside_events(self) -> None:
        trimmed = nfl_week_cache.trim_scoreboard(load_week())
        abbrs = {e["away"]["abbr"] for e in trimmed["events"]} | {
            e["home"]["abbr"] for e in trimmed["events"]
        }

        assert "WAS" in abbrs and "WSH" not in abbrs

    def test_in_progress_game_keeps_clock_period_and_situation(self) -> None:
        live = _event(nfl_week_cache.trim_scoreboard(load_week()), "900000001")

        assert live["state"] == "in"
        assert (live["period"], live["clock"]) == (3, "4:12")
        assert live["status_name"] == "STATUS_IN_PROGRESS"
        assert live["situation"]["down_distance"] == "3rd & 4"
        assert live["situation"]["possession"] == live["home"]["abbr"]

    def test_pregame_has_no_linescores(self) -> None:
        pre = _event(nfl_week_cache.trim_scoreboard(load_week()), "900000002")

        assert pre["state"] == "pre"
        assert pre["home"]["linescores"] == []
        assert pre["short_detail"] == "10/20 - 8:15 PM EDT"

    def test_postseason_is_out_of_scope(self) -> None:
        payload = load_week()
        payload["season"]["type"] = 3

        assert nfl_week_cache.trim_scoreboard(payload) is None

    def test_a_malformed_event_is_dropped_not_fatal(self) -> None:
        payload = load_week()
        payload["events"].append({"id": "broken"})

        assert len(nfl_week_cache.trim_scoreboard(payload)["events"]) == 4


class TestTrimProjections:
    def test_keeps_names_position_team_and_points(self) -> None:
        players = nfl_week_cache.trim_projections(load_projection_rows())

        chase = players["7564"]
        assert (chase["first_name"], chase["last_name"]) == ("Ja'Marr", "Chase")
        assert chase["position"] == "WR"
        assert chase["team"] == "CIN"
        assert chase["pts_ppr"] > chase["pts_std"]

    def test_drops_free_agents_and_zero_point_keys(self) -> None:
        rows = load_projection_rows()
        players = nfl_week_cache.trim_projections(rows)

        free_agent = next(r for r in rows if not r.get("team"))
        assert free_agent["player_id"] not in players
        zeros = [p for p in players.values() if "pts_ppr" not in p]
        assert zeros, "a zero-projection depth player is kept for his name"

    def test_normalizes_the_team(self) -> None:
        rows = [{"player_id": "1", "team": "WSH", "player": {"last_name": "X"}, "stats": {}}]

        assert nfl_week_cache.trim_projections(rows)["1"]["team"] == "WAS"


@pytest.mark.asyncio
async def test_store_and_read_round_trip_with_current_pointer(session_factory) -> None:
    trimmed = nfl_week_cache.trim_scoreboard(load_week())
    async with session_factory() as session:
        assert await nfl_week_cache.read_current(session) is None
        await nfl_week_cache.store_week(session, trimmed, current=True)

    async with session_factory() as session:
        assert await nfl_week_cache.read_current(session) == (2025, 7)
        payload, fetched_at = await nfl_week_cache.read_week(session, 2025, 7)
        assert payload == trimmed
        assert fetched_at is not None
        assert await nfl_week_cache.read_week(session, 2025, 8) is None


@pytest.mark.asyncio
async def test_store_week_without_current_leaves_the_pointer(session_factory) -> None:
    trimmed = nfl_week_cache.trim_scoreboard(load_week())
    async with session_factory() as session:
        await nfl_week_cache.store_week(session, trimmed, current=True)
        later = copy.deepcopy(trimmed) | {"week": 9}
        await nfl_week_cache.store_week(session, later)

    async with session_factory() as session:
        assert await nfl_week_cache.read_current(session) == (2025, 7)
        assert (await nfl_week_cache.read_week(session, 2025, 9))[0]["week"] == 9


@pytest.mark.asyncio
async def test_store_scoreboard_never_raises(session_factory) -> None:
    async with session_factory() as session:
        await nfl_week_cache.store_scoreboard(session, {"season": "garbage"}, current=True)
        await nfl_week_cache.store_scoreboard(session, {"events": None}, current=True)

        assert await nfl_week_cache.read_current(session) is None


@pytest.mark.asyncio
async def test_projections_round_trip(session_factory) -> None:
    players = nfl_week_cache.trim_projections(load_projection_rows())
    async with session_factory() as session:
        assert not await nfl_week_cache.has_projections(session, 2025, 7)
        assert await nfl_week_cache.read_projections(session, 2025, 7) == {}
        await nfl_week_cache.store_projections(session, 2025, 7, players)

    async with session_factory() as session:
        assert await nfl_week_cache.has_projections(session, 2025, 7)
        assert await nfl_week_cache.read_projections(session, 2025, 7) == players
