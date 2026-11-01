"""`platforms/nfl_weeks.py` — the `refresh_nfl_weeks` job's fetch policy (add-nfl-scores)."""

import copy
import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base
from backend.gridiron.platforms import nfl_weeks
from backend.gridiron.platforms.nfl_scoreboard import SCOREBOARD_URL
from backend.gridiron.platforms.sleeper import PROJECTIONS_BASE
from backend.gridiron.services import nfl_week_cache

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_week() -> dict:
    return json.loads((FIXTURES / "nfl" / "scores_week.json").read_text())


def load_projection_rows() -> list[dict]:
    return json.loads((FIXTURES / "sleeper" / "week_projections.json").read_text())["rows"]


def week_payload(week: int, *, final: bool = True) -> dict:
    """The fixture relabeled as `week`, with every game final (or every game pre)."""
    payload = copy.deepcopy(load_week())
    payload["week"]["number"] = week
    for event in payload["events"]:
        state = "post" if final else "pre"
        event["competitions"][0]["status"]["type"]["state"] = state
        event["competitions"][0]["status"]["type"]["name"] = (
            "STATUS_FINAL" if final else "STATUS_SCHEDULED"
        )
    return payload


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "nfl-weeks.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class TestScoreboardIsSettled:
    def test_uncached_week_is_never_settled(self) -> None:
        assert not nfl_weeks.scoreboard_is_settled(None, 3, 8)

    def test_current_and_future_weeks_are_never_settled(self) -> None:
        cached = {"events": [{"state": "post"}]}

        assert not nfl_weeks.scoreboard_is_settled(cached, 8, 8)
        assert not nfl_weeks.scoreboard_is_settled(cached, 9, 8)

    def test_past_week_with_every_game_over_is_settled(self) -> None:
        cached = {"events": [{"state": "post"}, {"state": "postponed"}]}

        assert nfl_weeks.scoreboard_is_settled(cached, 7, 8)

    def test_past_week_with_an_unfinished_game_is_refetched(self) -> None:
        cached = {"events": [{"state": "post"}, {"state": "pre"}]}

        assert not nfl_weeks.scoreboard_is_settled(cached, 7, 8)

    def test_past_week_with_no_games_is_refetched(self) -> None:
        assert not nfl_weeks.scoreboard_is_settled({"events": []}, 7, 8)


def _mock_upstreams() -> tuple[respx.Route, respx.Route]:
    def scoreboard(request: httpx.Request) -> httpx.Response:
        week = request.url.params.get("week")
        if week is None:
            return httpx.Response(200, json=week_payload(7, final=False))
        return httpx.Response(200, json=week_payload(int(week), final=int(week) < 7))

    scoreboard_route = respx.get(SCOREBOARD_URL).mock(side_effect=scoreboard)
    projections_route = respx.get(url__startswith=f"{PROJECTIONS_BASE}/2025/").mock(
        return_value=httpx.Response(200, json=load_projection_rows())
    )
    return scoreboard_route, projections_route


@pytest.mark.asyncio
@respx.mock
async def test_first_pass_learns_the_week_and_fills_the_season(session_factory) -> None:
    scoreboard_route, projections_route = _mock_upstreams()

    async with session_factory() as session:
        assert await nfl_weeks.fetch_and_cache(session) is None

    # One bare call to learn "current", then all 18 weeks; projections for all 18.
    assert scoreboard_route.call_count == 1 + 18
    assert projections_route.call_count == 18
    week_calls = [
        c.request.url.params for c in scoreboard_route.calls if "week" in c.request.url.params
    ]
    assert {p["seasontype"] for p in week_calls} == {"2"}
    assert {p["dates"] for p in week_calls} == {"2025"}
    async with session_factory() as session:
        assert await nfl_week_cache.read_current(session) == (2025, 7)
        assert (await nfl_week_cache.read_week(session, 2025, 12))[0]["week"] == 12
        assert "7564" in await nfl_week_cache.read_projections(session, 2025, 3)


@pytest.mark.asyncio
@respx.mock
async def test_second_pass_skips_finished_weeks(session_factory) -> None:
    scoreboard_route, projections_route = _mock_upstreams()
    async with session_factory() as session:
        await nfl_weeks.fetch_and_cache(session)
    scoreboard_route.reset()
    projections_route.reset()

    async with session_factory() as session:
        assert await nfl_weeks.fetch_and_cache(session) is None

    # Weeks 1-6 are final and cached; 7-18 still move. The current pointer is known now.
    fetched = sorted(int(c.request.url.params["week"]) for c in scoreboard_route.calls)
    assert fetched == list(range(7, 19))
    projected = sorted(int(c.request.url.path.rsplit("/", 1)[-1]) for c in projections_route.calls)
    assert projected == list(range(7, 19))


@pytest.mark.asyncio
@respx.mock
async def test_week_sweep_never_moves_the_current_pointer(session_factory) -> None:
    _mock_upstreams()
    async with session_factory() as session:
        await nfl_week_cache.store_week(
            session, nfl_week_cache.trim_scoreboard(week_payload(5, final=False)), current=True
        )
        await nfl_weeks.fetch_and_cache(session)

    async with session_factory() as session:
        assert await nfl_week_cache.read_current(session) == (2025, 5)


@pytest.mark.asyncio
@respx.mock
async def test_http_error_is_reported_not_raised(session_factory) -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(503))

    async with session_factory() as session:
        error = await nfl_weeks.fetch_and_cache(session)

    assert error is not None and error.startswith("nfl weeks unavailable")


@pytest.mark.asyncio
@respx.mock
async def test_off_season_payload_is_a_quiet_no_op(session_factory) -> None:
    payload = load_week()
    payload["season"]["type"] = 3
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    async with session_factory() as session:
        assert await nfl_weeks.fetch_and_cache(session) is None
        assert await nfl_week_cache.read_current(session) is None
