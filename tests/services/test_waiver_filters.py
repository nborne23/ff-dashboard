"""The Waivers filter sheet: `services/waiver_filters.py` and the options it adds to
`fantasy_service.get_waivers` (status, Show My Team, game day, sort)."""

import json
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron import schemas
from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    League,
    LiveNflGame,
    Player,
    PlayerPoolEntry,
    RosterSlot,
    Team,
)
from backend.gridiron.services import fantasy_service, waiver_filters
from backend.gridiron.services.waiver_filters import ScheduledGame

LEAGUE = "espn:5555555"
MY_TEAM = "espn:l-5555555-t-1"
RIVAL_TEAM = "espn:l-5555555-t-2"
WEEK = 9

# Week 9 of a 2026 season: TNF Thu Nov 5 (8:15pm ET = 01:15 UTC Friday), Sunday Nov 8,
# MNF Mon Nov 9 (8:15pm ET = 01:15 UTC Tuesday).
TNF = datetime(2026, 11, 6, 1, 15)
SUNDAY_EARLY = datetime(2026, 11, 8, 18, 0)
SUNDAY_LATE = datetime(2026, 11, 8, 21, 25)
MNF = datetime(2026, 11, 10, 1, 15)
LAST_MNF = datetime(2026, 11, 3, 1, 15)


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "waiver-filters.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _player(pid: str, name: str, position: str, nfl_team: str, bye: int = 12) -> Player:
    return Player(
        id=pid,
        platform="espn",
        platform_id=pid.split("-")[-1],
        name=name,
        position=position,
        nfl_team=nfl_team,
        nfl_opponent=None,
        nfl_game_id=None,
        bye_week=bye,
        injury_status="ACTIVE",
    )


def _team(team_id: str, name: str, *, mine: bool) -> Team:
    return Team(
        id=team_id,
        league_id=LEAGUE,
        platform="espn",
        platform_id=team_id.split("-")[-1],
        name=name,
        manager_name="Manager",
        rank_current=1,
        rank_total=10,
        is_user_team=mine,
    )


def _slot(team_id: str, slot: str, pid: str) -> RosterSlot:
    return RosterSlot(
        team_id=team_id,
        week=WEEK,
        slot=slot,
        player_id=pid,
        proj_points=10.0,
        actual_points=0.0,
        is_live=False,
        game_state=None,
        status_text="",
    )


def _pool(pid: str, status: str, season_proj: float | None, owned: float, **extra):
    eligible = extra.pop("eligible", ["RB", "RB/WR", "FLEX", "BN", "IR"])
    return PlayerPoolEntry(
        league_id=LEAGUE,
        player_id=pid,
        status=status,
        on_team_id=extra.pop("on_team_id", None),
        percent_owned=owned,
        percent_started=0.0,
        season_proj_points=season_proj,
        eligible_slots=json.dumps(eligible),
        **extra,
    )


def _game(game_id: str, home: str, away: str, kickoff: datetime, state: str = "pre"):
    return LiveNflGame(
        nfl_game_id=game_id,
        home_team=home,
        away_team=away,
        home_score=0,
        away_score=0,
        state=state,
        clock=None,
        period=None,
        kickoff_at=kickoff,
    )


async def _seed(session_factory, *, sunday_state: str = "pre", tnf_state: str = "pre") -> None:
    """Two teams in one ESPN league. I start one RB (season 100); my rival rosters a
    better one. The pool has a free agent and a waiver player, on teams playing Thursday,
    Sunday and Monday, plus a free agent whose team is on bye."""
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE,
                platform="espn",
                platform_id="5555555",
                name="Filter League",
                season=2026,
                team_count=10,
                scoring_type="ppr",
                current_week=WEEK,
            )
        )
        session.add(_team(MY_TEAM, "My Team", mine=True))
        session.add(_team(RIVAL_TEAM, "Rival Squad", mine=False))

        session.add(_player("espn:p-1", "My Starter", "RB", "DAL"))
        session.add(_player("espn:p-2", "My Bench WR", "WR", "DAL"))
        session.add(_player("espn:p-3", "Rival Star", "RB", "PHI"))
        session.add(_slot(MY_TEAM, "RB1", "espn:p-1"))
        session.add(_slot(MY_TEAM, "BN", "espn:p-2"))
        session.add(_slot(RIVAL_TEAM, "RB1", "espn:p-3"))
        session.add(_pool("espn:p-1", "ONTEAM", 100.0, 99.0, on_team_id="1"))
        # The rival's star has no pool row at all — the shape every Yahoo rostered player
        # has, since Yahoo's pool is fetched available-only.

        session.add(_player("espn:p-10", "Thursday FA", "RB", "PIT"))
        session.add(_player("espn:p-11", "Sunday Waiver", "RB", "WAS"))
        session.add(_player("espn:p-12", "Monday FA", "RB", "KC"))
        session.add(_player("espn:p-13", "Bye Week FA", "RB", "SF", bye=WEEK))
        session.add(_pool("espn:p-10", "FREEAGENT", 130.0, 12.0))
        session.add(_pool("espn:p-11", "WAIVERS", 150.0, 40.0, waiver_clears=date(2026, 11, 4)))
        session.add(_pool("espn:p-12", "FREEAGENT", 110.0, 55.0))
        session.add(_pool("espn:p-13", "FREEAGENT", 170.0, 30.0))

        session.add(_game("g-tnf", "PIT", "CLE", TNF, tnf_state))
        # The scoreboard calls Washington "WSH"; rosters say "WAS".
        session.add(_game("g-sun", "WSH", "DAL", SUNDAY_EARLY, sunday_state))
        session.add(_game("g-sun2", "PHI", "NYG", SUNDAY_LATE, sunday_state))
        session.add(_game("g-mnf", "KC", "DEN", MNF))
        # SF's latest row is last week's Monday night — they're on bye this week.
        session.add(_game("g-old", "SF", "SEA", LAST_MNF, "post"))
        await session.commit()


def _names(data: schemas.WaiversData) -> list[str]:
    return [c.player.name for c in data.candidates]


# --- pure helpers ---------------------------------------------------------------------


def test_game_date_is_the_eastern_day_not_the_utc_one() -> None:
    """TNF at 8:15pm ET is already Friday in UTC; it must bucket as Thursday."""
    assert waiver_filters.game_date(TNF) == date(2026, 11, 5)
    assert waiver_filters.game_date(MNF) == date(2026, 11, 9)


def test_week_schedule_keeps_each_team_s_newest_game_within_the_week() -> None:
    rows = [
        ("WSH", "DAL", "pre", SUNDAY_EARLY),
        ("DAL", "NYG", "post", datetime(2026, 11, 2, 18, 0)),  # DAL's previous week
        ("SF", "SEA", "post", LAST_MNF),  # SF's newest is last week: on bye now
        ("KC", "DEN", "pre", MNF),
    ]

    schedule = waiver_filters.week_schedule(rows, lambda abbr: {"WSH": "WAS"}.get(abbr, abbr))

    assert schedule["DAL"] == ScheduledGame(SUNDAY_EARLY, "pre")
    assert "WAS" in schedule and "WSH" not in schedule
    assert "SF" not in schedule and "SEA" not in schedule
    assert waiver_filters.week_schedule([], str) == {}


def test_remaining_game_days_drops_a_day_whose_games_are_all_final() -> None:
    schedule = {
        "PIT": ScheduledGame(TNF, "post"),
        "DAL": ScheduledGame(SUNDAY_EARLY, "post"),
        "PHI": ScheduledGame(SUNDAY_LATE, "in"),
        "KC": ScheduledGame(MNF, "pre"),
    }

    assert waiver_filters.remaining_game_days(schedule) == [date(2026, 11, 8), date(2026, 11, 9)]


def test_fallback_eligibility_adds_flex_only_for_flex_positions() -> None:
    assert waiver_filters.fallback_eligibility("WR") == ["WR", "FLEX"]
    assert waiver_filters.fallback_eligibility("QB") == ["QB"]


def test_sort_key_puts_unrankable_rows_last_on_every_axis() -> None:
    def key(sort, **values):
        defaults = dict(
            delta=None, season_points=None, week_delta=None, week_points=None, percent_owned=None
        )
        return waiver_filters.sort_key(sort, **{**defaults, **values})

    assert key("owned", percent_owned=5.0) < key("owned", percent_owned=None)
    assert key("owned", percent_owned=60.0) < key("owned", percent_owned=5.0)
    assert key("upgrade_week", week_delta=3.0) < key("upgrade_week", week_delta=-1.0)
    assert key("upgrade", delta=1.0) < key("upgrade", delta=None, season_points=500.0)


# --- get_waivers ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_lists_the_claimable_pool_with_its_waiver_dates(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK)

    assert _names(data) == ["Bye Week FA", "Sunday Waiver", "Thursday FA", "Monday FA"]
    waiver = next(c for c in data.candidates if c.status == "WAIVERS")
    assert waiver.waiver_clears == date(2026, 11, 4)
    assert not any(c.is_mine or c.rostered_by for c in data.candidates)


@pytest.mark.asyncio
async def test_status_narrows_to_free_agents_or_waivers(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        free_agents = await fantasy_service.get_waivers(
            session, MY_TEAM, WEEK, status="free_agents"
        )
        waivers = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, status="waivers")

    assert "Sunday Waiver" not in _names(free_agents)
    assert {c.status for c in free_agents.candidates} == {"FREEAGENT"}
    assert _names(waivers) == ["Sunday Waiver"]


@pytest.mark.asyncio
async def test_all_players_adds_every_roster_with_its_owner(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, status="all")

    by_name = {c.player.name: c for c in data.candidates}
    rival = by_name["Rival Star"]
    assert (rival.status, rival.rostered_by, rival.is_mine) == ("ONTEAM", "Rival Squad", False)
    # No pool row: ownership is unknown, not zero, and eligibility falls back to the
    # position so the player can still be compared against my RB starter.
    assert rival.percent_owned is None
    assert rival.eligible_slots == ["RB", "FLEX"]
    assert by_name["My Starter"].is_mine is True
    assert "Thursday FA" in by_name  # the claimable pool is still listed


@pytest.mark.asyncio
async def test_show_my_team_adds_only_my_roster(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, include_mine=True)

    mine = [c for c in data.candidates if c.is_mine]
    assert {c.player.name for c in mine} == {"My Starter", "My Bench WR"}
    assert all(c.rostered_by == "My Team" for c in mine)
    assert "Rival Star" not in _names(data)
    # My starter, measured against my weakest RB starter (himself), is exactly level.
    starter = next(c for c in mine if c.player.name == "My Starter")
    assert starter.delta_vs_worst_starter == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_show_my_team_respects_the_position_filter(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(
            session, MY_TEAM, WEEK, position="WR", include_mine=True
        )

    assert _names(data) == ["My Bench WR"]


@pytest.mark.asyncio
async def test_game_days_and_the_game_day_filter(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        everyone = await fantasy_service.get_waivers(session, MY_TEAM, WEEK)
        thursday = await fantasy_service.get_waivers(
            session, MY_TEAM, WEEK, game_day=date(2026, 11, 5)
        )
        sunday = await fantasy_service.get_waivers(
            session, MY_TEAM, WEEK, game_day=date(2026, 11, 8)
        )

    assert everyone.game_days == [date(2026, 11, 5), date(2026, 11, 8), date(2026, 11, 9)]
    assert everyone.game_day is None
    assert _names(thursday) == ["Thursday FA"]
    assert thursday.game_day == date(2026, 11, 5)
    # "WSH" on the scoreboard matches "WAS" on the roster; the bye-week FA is never
    # listed under a game day.
    assert _names(sunday) == ["Sunday Waiver"]


@pytest.mark.asyncio
async def test_a_game_day_with_nothing_left_to_play_is_dropped_not_applied(
    session_factory,
) -> None:
    """A filter remembered from Thursday is stale by Saturday. Answering it with an empty
    list would read as "nobody is available"; the filter is dropped instead, and
    `game_day` says so."""
    await _seed(session_factory, tnf_state="post")

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, game_day=date(2026, 11, 5))

    assert date(2026, 11, 5) not in data.game_days
    assert data.game_day is None
    assert len(data.candidates) == 4


@pytest.mark.asyncio
async def test_only_the_current_week_has_game_days(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(
            session, MY_TEAM, WEEK + 1, game_day=date(2026, 11, 8)
        )

    assert data.game_days == []
    assert data.game_day is None


@pytest.mark.asyncio
async def test_sort_by_percent_rostered(session_factory) -> None:
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, sort="owned")

    assert [c.percent_owned for c in data.candidates] == [55.0, 40.0, 30.0, 12.0]


@pytest.mark.asyncio
async def test_filters_apply_before_the_limit(session_factory) -> None:
    """The point of filtering server-side: a narrow filter searches the whole pool, not
    the top-N shortlist. The waiver player ranks second overall, so a limit of one would
    lose him if the cut came first."""
    await _seed(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, MY_TEAM, WEEK, limit=1, status="waivers")

    assert _names(data) == ["Sunday Waiver"]


# --- Yahoo's waiver overlay -------------------------------------------------------------


class _FakeYahoo:
    def __init__(self, items=None, error: Exception | None = None) -> None:
        self.items = items or []
        self.error = error

    async def list_waiver_players_raw(self, session, league_key):
        if self.error:
            raise self.error
        return self.items


def _yahoo_entry(key: str) -> schemas.PlayerPoolEntry:
    return schemas.PlayerPoolEntry(
        league_id="",
        player=schemas.Player(
            id=f"yahoo:{key}",
            name=key,
            position="WR",
            nfl_team="MIA",
            nfl_opponent=None,
            nfl_game_id=None,
            headshot_url="",
            bye_week=None,
            injury_status=None,
        ),
        status="FREEAGENT",
        on_team_id=None,
        percent_owned=10.0,
        percent_started=0.0,
        season_proj_points=None,
    )


def _waiver_item(key: str, waiver_date: str) -> dict:
    return {
        "player": [
            [{"player_key": key}, {"name": {"full": key}}],
            {"ownership": {"ownership_type": "waivers", "waiver_date": waiver_date}},
        ]
    }


@pytest.mark.asyncio
async def test_yahoo_overlay_marks_waiver_players_with_their_clear_date() -> None:
    league = League(id="yahoo:461.l.1", platform="yahoo", platform_id="461.l.1", name="Y")
    entries = [_yahoo_entry("461.p.1"), _yahoo_entry("461.p.2")]
    client = _FakeYahoo(items=[_waiver_item("461.p.2", "2026-11-04")])

    result = await fantasy_service._overlay_yahoo_waivers(client, None, league, entries)

    assert [(e.status, e.waiver_clears) for e in result] == [
        ("FREEAGENT", None),
        ("WAIVERS", date(2026, 11, 4)),
    ]


@pytest.mark.asyncio
async def test_yahoo_overlay_failure_keeps_the_pool_as_free_agents() -> None:
    league = League(id="yahoo:461.l.1", platform="yahoo", platform_id="461.l.1", name="Y")
    entries = [_yahoo_entry("461.p.1")]
    client = _FakeYahoo(error=httpx.ConnectError("down"))

    result = await fantasy_service._overlay_yahoo_waivers(client, None, league, entries)

    assert result == entries


@pytest.mark.asyncio
async def test_yahoo_overlay_survives_an_unexpected_error_type() -> None:
    league = League(id="yahoo:461.l.1", platform="yahoo", platform_id="461.l.1", name="Y")
    entries = [_yahoo_entry("461.p.1")]
    client = _FakeYahoo(error=RuntimeError("yahoo rejected the request"))

    assert await fantasy_service._overlay_yahoo_waivers(client, None, league, entries) == entries


@pytest.mark.asyncio
async def test_yahoo_overlay_survives_a_malformed_ownership_shape() -> None:
    league = League(id="yahoo:461.l.1", platform="yahoo", platform_id="461.l.1", name="Y")
    entries = [_yahoo_entry("461.p.1")]
    malformed = {"player": [[{"player_key": "461.p.1"}], {"ownership": "waivers"}]}
    client = _FakeYahoo(items=[malformed])

    assert await fantasy_service._overlay_yahoo_waivers(client, None, league, entries) == entries
