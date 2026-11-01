"""`services/scores.py` — the Scores screen's week and game read models (add-nfl-scores).

Seeded from payloads captured off ESPN and Sleeper for 2025 week 7 (PIT @ CIN), so the
names and numbers asserted here are real ones.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, PlayerWeeklyStat, RosterSlot, Team
from backend.gridiron.platforms.sleeper_stats import map_row
from backend.gridiron.services import nfl_week_cache, scores

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FETCHED_AT = datetime(2025, 10, 17, 4, 0)

FINAL_GAME = "401772941"  # PIT @ CIN, final 31-33
LIVE_GAME = "900000001"
PRE_GAME = "900000002"


def load_week() -> dict:
    return json.loads((FIXTURES / "nfl" / "scores_week.json").read_text())


def load_rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / "sleeper" / name).read_text())["rows"]


def relabeled(week: int, state: str) -> dict:
    """The fixture as another week, with PIT @ CIN rewritten into `state`."""
    payload = copy.deepcopy(load_week())
    payload["week"]["number"] = week
    event = next(e for e in payload["events"] if e["id"] == FINAL_GAME)
    status = event["competitions"][0]["status"]
    if state == "pre":
        status["type"] = {"name": "STATUS_SCHEDULED", "state": "pre", "shortDetail": "Thu 8:15"}
        for competitor in event["competitions"][0]["competitors"]:
            competitor["score"] = "0"
            competitor.pop("winner", None)
    elif state == "in":
        status["type"] = {"name": "STATUS_IN_PROGRESS", "state": "in", "shortDetail": "2:00 - 2nd"}
        status["period"], status["displayClock"] = 2, "2:00"
    return payload


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "scores.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed(session, *, scoring: str = "ppr") -> None:
    """Week 7 cached and current; CIN/PIT stat lines and projections; one ESPN league
    where the user rosters Joe Flacco and a rival rosters Ja'Marr Chase."""
    await nfl_week_cache.store_week(
        session, nfl_week_cache.trim_scoreboard(load_week()), current=True
    )
    projections = nfl_week_cache.trim_projections(load_rows("week_projections.json"))
    await nfl_week_cache.store_projections(session, 2025, 7, projections)
    for row in load_rows("week_stats.json"):
        values = map_row(row, season=2025, week=7, fetched_at=FETCHED_AT)
        if values is not None:
            session.add(PlayerWeeklyStat(**values))

    session.add_all(
        [
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="Alpha League",
                season=2025,
                team_count=10,
                scoring_type=scoring,
                current_week=7,
            ),
            League(
                id="yahoo:2",
                platform="yahoo",
                platform_id="2",
                name="Bravo League",
                season=2025,
                team_count=12,
                scoring_type="custom",
                current_week=7,
            ),
            League(
                id="espn:3",
                platform="espn",
                platform_id="3",
                name="Disabled League",
                season=2025,
                team_count=8,
                scoring_type="ppr",
                current_week=7,
                is_enabled=False,
            ),
            Team(
                id="espn:l-1-t-1",
                league_id="espn:1",
                platform="espn",
                platform_id="l-1-t-1",
                name="Scranton Stranglers",
                manager_name="Nick",
                rank_current=8,
                rank_total=10,
                is_user_team=True,
            ),
            Team(
                id="espn:l-1-t-2",
                league_id="espn:1",
                platform="espn",
                platform_id="l-1-t-2",
                name="Da Bears",
                manager_name="Jakub",
                rank_current=6,
                rank_total=10,
            ),
            Team(
                id="yahoo:2.t.1",
                league_id="yahoo:2",
                platform="yahoo",
                platform_id="2.t.1",
                name="Yahoo Mine",
                manager_name="Nick",
                rank_current=1,
                rank_total=12,
                is_user_team=True,
            ),
            Player(
                id="espn:p-11252",
                platform="espn",
                platform_id="p-11252",
                name="Joe Flacco",
                position="QB",
                nfl_team="CIN",
                sleeper_id="19",
            ),
            Player(
                id="yahoo:461.p.8780",
                platform="yahoo",
                platform_id="461.p.8780",
                name="Joe Flacco",
                position="QB",
                nfl_team="CIN",
                sleeper_id="19",
            ),
            Player(
                id="espn:p-4362628",
                platform="espn",
                platform_id="p-4362628",
                name="Ja'Marr Chase",
                position="WR",
                nfl_team="CIN",
                sleeper_id="7564",
            ),
            RosterSlot(
                team_id="espn:l-1-t-1",
                week=7,
                slot="QB",
                player_id="espn:p-11252",
                proj_points=18.0,
                actual_points=27.5,
            ),
            RosterSlot(
                team_id="espn:l-1-t-2",
                week=7,
                slot="WR",
                player_id="espn:p-4362628",
                proj_points=21.0,
                actual_points=40.1,
            ),
        ]
    )
    await session.commit()


def _side(detail, position: str, side: str):
    group = next(g for g in detail.groups if g.position == position)
    return getattr(group, side)


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------


class TestStatusText:
    @pytest.mark.parametrize(
        ("event", "expected"),
        [
            ({"state": "post", "period": 4}, "Final"),
            ({"state": "post", "period": 5}, "Final/OT"),
            ({"state": "postponed"}, "Postponed"),
            ({"state": "in", "status_name": "STATUS_HALFTIME", "period": 2}, "Half"),
            ({"state": "in", "status_name": "STATUS_END_PERIOD", "period": 1}, "End Q1"),
            ({"state": "in", "status_name": "X", "period": 3, "clock": "4:12"}, "Q3 4:12"),
            ({"state": "in", "status_name": "X", "period": 5, "clock": "9:00"}, "OT 9:00"),
            ({"state": "in", "status_name": "X", "period": 6, "clock": None}, "2OT"),
            ({"state": "pre", "short_detail": "10/20 - 8:15 PM EDT"}, "10/20 - 8:15 PM EDT"),
        ],
    )
    def test_cases(self, event: dict, expected: str) -> None:
        assert scores.status_text(event) == expected


class TestStatLine:
    def _line(self, stats: dict, position: str) -> list[tuple[str, str]]:
        return [(t.value, t.label) for t in scores._tokens(stats, position)]

    def test_quarterback_passes_then_runs(self) -> None:
        stats = {"pass_cmp": 24, "pass_att": 31, "pass_yd": 321, "pass_td": 2, "pass_int": 1}
        stats |= {"rush_att": 4, "rush_yd": 26, "rush_td": 1}

        assert self._line(stats, "QB") == [
            ("24/31", "CMP"),
            ("321", "YD"),
            ("2", "TD"),
            ("1", "INT"),
            ("4", "CAR"),
            ("26", "YD"),
            ("1", "TD"),
        ]

    def test_running_back_runs_then_catches_with_targets(self) -> None:
        stats = {"rush_att": 22, "rush_yd": 78, "rush_td": 1, "rec": 4, "rec_tgt": 4, "rec_yd": 12}

        assert self._line(stats, "RB") == [
            ("22", "CAR"),
            ("78", "YD"),
            ("1", "TD"),
            ("4/4", "REC"),
            ("12", "YD"),
        ]

    def test_receiver_without_targets_and_a_lost_fumble(self) -> None:
        assert self._line({"rec": 5, "rec_yd": 93, "fum_lost": 1}, "WR") == [
            ("5", "REC"),
            ("93", "YD"),
            ("1", "FUM"),
        ]

    def test_kicker_and_defense(self) -> None:
        assert self._line({"fgm": 2, "fga": 3, "xpm": 3, "xpa": 3, "fgm_lng": 52}, "K") == [
            ("2/3", "FG"),
            ("3/3", "XP"),
            ("52", "LNG"),
        ]
        assert self._line({"sack": 3, "int": 1, "pts_allow": 0}, "DEF") == [
            ("3", "SACK"),
            ("1", "INT"),
            ("0", "PA"),
        ]

    def test_fractional_values_keep_one_decimal(self) -> None:
        assert self._line({"sack": 1.5}, "DEF") == [("1.5", "SACK")]


# --------------------------------------------------------------------------------------
# Week
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_week_before_anything_is_cached(db) -> None:
    async with db() as session:
        week = await scores.week_scores(session, None)

    assert (week.season, week.week, week.current_week) == (None, 1, None)
    assert week.games == [] and week.fetched_at is None
    assert week.weeks == list(range(1, 19))


@pytest.mark.asyncio
async def test_week_defaults_to_current_and_orders_by_kickoff(db) -> None:
    async with db() as session:
        await seed(session)
        week = await scores.week_scores(session, None)

    assert (week.season, week.week, week.current_week) == (2025, 7, 7)
    assert week.byes == ["BAL", "BUF"]
    kickoffs = [g.kickoff_at for g in week.games]
    assert kickoffs == sorted(kickoffs)
    assert all(k.tzinfo is not None for k in kickoffs)
    assert week.fetched_at is not None and week.fetched_at.tzinfo is not None


@pytest.mark.asyncio
async def test_week_game_shapes(db) -> None:
    async with db() as session:
        await seed(session)
        games = {g.game_id: g for g in (await scores.week_scores(session, 7)).games}

    final = games[FINAL_GAME]
    assert (final.away.abbr, final.home.abbr) == ("PIT", "CIN")
    assert (final.away.score, final.home.score) == (31, 33)
    assert final.home.winner and not final.away.winner
    assert final.status_text == "Final"
    assert final.top_performer.short_name == "J. Flacco"
    assert final.top_performer.headshot_url == "/api/headshots/espn/11252.png"
    assert final.period is None and final.possession is None

    live = games[LIVE_GAME]
    assert live.status_text == "Q3 4:12"
    assert (live.period, live.clock, live.down_distance) == (3, "4:12", "3rd & 4")
    assert live.possession == live.home.abbr
    assert not live.home.winner and not live.away.winner

    pre = games[PRE_GAME]
    assert pre.away.score is None and pre.home.score is None
    assert pre.top_performer is None


@pytest.mark.asyncio
async def test_uncached_week_is_empty_not_an_error(db) -> None:
    async with db() as session:
        await seed(session)
        week = await scores.week_scores(session, 12)

    assert week.week == 12 and week.games == [] and week.fetched_at is None


# --------------------------------------------------------------------------------------
# Game detail
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_game_is_none(db) -> None:
    async with db() as session:
        await seed(session)
        assert await scores.game_detail(session, "nope", None) is None


@pytest.mark.asyncio
async def test_detail_lists_enabled_leagues_and_defaults_to_the_first(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, None)

    assert [lg.league_id for lg in detail.leagues] == ["espn:1", "yahoo:2"]
    assert detail.leagues[0].team_id == "espn:l-1-t-1"
    assert detail.league_id == "espn:1"
    assert (detail.season, detail.week) == (2025, 7)
    assert detail.stats_as_of == FETCHED_AT.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_rostered_players_show_the_leagues_own_numbers(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1")

    flacco = _side(detail, "QB", "home")[0]
    assert flacco.short_name == "J. Flacco"
    assert (flacco.points, flacco.projection, flacco.source) == (27.5, 18.0, "league")
    assert flacco.is_mine and flacco.fantasy_team == "Scranton Stranglers"
    assert flacco.player is not None and flacco.player.id == "espn:p-11252"
    assert flacco.stat_line[0].label == "CMP"

    chase = _side(detail, "WR", "home")[0]
    assert chase.name == "Ja'Marr Chase"
    assert (chase.points, chase.source, chase.is_mine) == (40.1, "league", False)
    assert chase.fantasy_team == "Da Bears"


@pytest.mark.asyncio
async def test_everyone_else_is_estimated_in_the_leagues_format(db) -> None:
    async with db() as session:
        await seed(session, scoring="half_ppr")
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1")

    assert (detail.points_format, detail.points_format_fallback) == ("half_ppr", False)
    rodgers = _side(detail, "QB", "away")[0]
    assert rodgers.short_name == "A. Rodgers"
    assert rodgers.source == "estimated"
    assert rodgers.player is None and rodgers.fantasy_team is None
    higgins = next(p for p in _side(detail, "WR", "home") if p.sleeper_id == "6801")
    stats_row = next(r for r in load_rows("week_stats.json") if r["player_id"] == "6801")
    assert higgins.points == round(stats_row["stats"]["pts_half_ppr"], 2)


@pytest.mark.asyncio
async def test_custom_league_falls_back_to_ppr_and_says_so(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, "yahoo:2")

    assert detail.league_id == "yahoo:2"
    assert (detail.points_format, detail.points_format_fallback) == ("ppr", True)
    # Not rostered in this league: Flacco is estimated here, and the Yahoo row is his card.
    flacco = _side(detail, "QB", "home")[0]
    assert flacco.source == "estimated" and flacco.points == 25.98
    assert flacco.player.id == "yahoo:461.p.8780"


@pytest.mark.asyncio
async def test_positions_ordered_and_sorted_by_points(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1")

    assert [g.position for g in detail.groups] == ["QB", "RB", "WR", "TE", "K", "DEF"]
    for group in detail.groups:
        for side in (group.away, group.home):
            points = [p.points for p in side]
            assert points == sorted(points, reverse=True)
            assert all(p.team == ("PIT" if side is group.away else "CIN") for p in side)


@pytest.mark.asyncio
async def test_final_game_lists_only_players_who_played(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1")

    played = {r["player_id"] for r in load_rows("week_stats.json")}
    listed = {p.sleeper_id for g in detail.groups for p in g.away + g.home}
    assert listed <= played
    assert all(p.points is not None for g in detail.groups for p in g.away + g.home)


@pytest.mark.asyncio
async def test_defense_is_named_for_the_team(db) -> None:
    async with db() as session:
        await seed(session)
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1")

    bengals = _side(detail, "DEF", "home")[0]
    assert (bengals.name, bengals.short_name) == ("Cincinnati Bengals", "Bengals")
    assert any(t.label == "PA" for t in bengals.stat_line)


@pytest.mark.asyncio
async def test_pregame_lists_projected_players_without_points(db) -> None:
    async with db() as session:
        await seed(session)
        await nfl_week_cache.store_week(
            session, nfl_week_cache.trim_scoreboard(relabeled(8, "pre"))
        )
        await nfl_week_cache.store_projections(
            session,
            2025,
            8,
            nfl_week_cache.trim_projections(load_rows("week_projections.json")),
        )
        detail = await scores.game_detail(session, FINAL_GAME, "espn:1", week=8)

    assert detail.week == 8 and detail.game.state == "pre"
    players = [p for g in detail.groups for p in g.away + g.home]
    assert players and all(p.points is None for p in players)
    assert all(p.projection and p.projection >= scores.MIN_LISTED_PROJECTION for p in players)
    for group in detail.groups:
        projections = [p.projection for p in group.home]
        assert projections == sorted(projections, reverse=True)


@pytest.mark.asyncio
async def test_live_game_shows_projected_players_at_zero_until_they_record_a_stat(db) -> None:
    async with db() as session:
        await seed(session)
        await nfl_week_cache.store_week(session, nfl_week_cache.trim_scoreboard(relabeled(9, "in")))
        await nfl_week_cache.store_projections(
            session,
            2025,
            9,
            nfl_week_cache.trim_projections(load_rows("week_projections.json")),
        )
        session.add(
            PlayerWeeklyStat(
                sleeper_id="7564",
                season=2025,
                week=9,
                team="CIN",
                opponent="PIT",
                pts_ppr=12.3,
                pts_half_ppr=10.8,
                pts_std=9.3,
                stats_json=json.dumps({"gp": 1, "rec": 3, "rec_tgt": 4, "rec_yd": 63}),
                fetched_at=FETCHED_AT,
            )
        )
        await session.commit()
        detail = await scores.game_detail(session, FINAL_GAME, "yahoo:2", week=9)

    assert detail.game.status_text == "Q2 2:00"
    receivers = _side(detail, "WR", "home")
    assert receivers[0].sleeper_id == "7564" and receivers[0].points == 12.3
    assert [t.value for t in receivers[0].stat_line[:2]] == ["3/4", "63"]
    others = [p for p in receivers[1:]]
    assert others and all(p.points == 0.0 and p.stat_line == [] for p in others)


@pytest.mark.asyncio
async def test_no_leagues_means_ppr_and_no_selection(db) -> None:
    async with db() as session:
        await nfl_week_cache.store_week(
            session, nfl_week_cache.trim_scoreboard(load_week()), current=True
        )
        detail = await scores.game_detail(session, FINAL_GAME, None)

    assert detail.leagues == [] and detail.league_id is None
    assert (detail.points_format, detail.points_format_fallback) == ("ppr", False)
    assert detail.groups == []
