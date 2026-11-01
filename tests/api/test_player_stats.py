"""`GET /api/players/{player_id}/stats` and the breakdown/summary logic behind it
(add-player-stats)."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import (
    Base,
    League,
    LiveNflGame,
    Player,
    PlayerProjection,
    PlayerWeeklyStat,
    RosterSlot,
    Team,
)
from backend.gridiron.platforms.espn.client import (
    ROSTER_MATCHUP_ENDPOINT,
    EspnClient,
    roster_matchup_params,
)
from backend.gridiron.schemas.player_stats import GameLogRow
from backend.gridiron.services import cache, fantasy_service, player_stats
from backend.main import app

FETCHED_AT = datetime(2026, 10, 22, 12, 0)


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "player-stats-api.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(db) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


def weekly(sleeper_id, season, week, ppr, half, std, team="NE", opp="NYJ", **stats):
    return PlayerWeeklyStat(
        sleeper_id=sleeper_id,
        season=season,
        week=week,
        team=team,
        opponent=opp,
        game_date=f"{season}-10-0{week % 9 + 1}",
        pts_ppr=ppr,
        pts_half_ppr=half,
        pts_std=std,
        stats_json=json.dumps({"gp": 1.0, **stats}),
        fetched_at=FETCHED_AT,
    )


def espn_roster_payload(espn_id: int, week: int) -> dict:
    """The slice of a `roster_matchup` payload the read path walks."""
    return {
        "teams": [
            {
                "roster": {
                    "entries": [
                        {
                            "playerPoolEntry": {
                                "player": {
                                    "id": espn_id,
                                    "stats": [
                                        # A projection for the same week — must be ignored.
                                        {
                                            "scoringPeriodId": week,
                                            "statSourceId": 1,
                                            "statSplitTypeId": 1,
                                            "appliedStats": {"3": 9.9},
                                            "stats": {"3": 250.0},
                                        },
                                        {
                                            "scoringPeriodId": week,
                                            "statSourceId": 0,
                                            "statSplitTypeId": 1,
                                            "appliedTotal": 10.32,
                                            "appliedStats": {
                                                "3": 4.12,
                                                "20": -2.0,
                                                "24": 2.2,
                                                "25": 6.0,
                                                "999": 0.0,
                                            },
                                            "stats": {
                                                "0": 13.0,
                                                "1": 10.0,
                                                "3": 103.0,
                                                "20": 1.0,
                                                "23": 3.0,
                                                "24": 22.0,
                                                "25": 1.0,
                                            },
                                        },
                                    ],
                                }
                            }
                        }
                    ]
                }
            }
        ]
    }


async def seed(db, scoring="half_ppr", with_espn_cache=True) -> None:
    async with db() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=2026,
                team_count=10,
                scoring_type=scoring,
                current_week=7,
            )
        )
        for team_id in ("espn:l-1-t-1", "espn:l-1-t-2"):
            session.add(
                Team(
                    id=team_id,
                    league_id="espn:1",
                    platform="espn",
                    platform_id=team_id,
                    name=team_id,
                    manager_name="m",
                    rank_current=1,
                    rank_total=10,
                )
            )
        session.add_all(
            [
                Player(
                    id="espn:p-4431452",
                    platform="espn",
                    platform_id="p-4431452",
                    name="Drake Maye",
                    position="QB",
                    nfl_team="NE",
                    nfl_opponent="CHI",
                    sleeper_id="11564",
                ),
                Player(
                    id="yahoo:470.p.1",
                    platform="yahoo",
                    platform_id="470.p.1",
                    name="Unmatched Guy",
                    position="WR",
                    nfl_team="FA",
                ),
            ]
        )
        # On the OTHER team in the league — an opponent's player seen from Matchups.
        session.add(
            RosterSlot(
                team_id="espn:l-1-t-2",
                week=7,
                slot="QB",
                player_id="espn:p-4431452",
                proj_points=20.6,
                actual_points=10.32,
                is_live=True,
                status_text="Q3 4:12",
            )
        )
        session.add_all(
            [
                weekly("11564", 2025, 1, 16.8, 16.8, 16.8, pass_yd=287.0, pass_td=1.0),
                weekly("11564", 2025, 2, 26.3, 26.3, 26.3, pass_yd=300.0, pass_td=2.0),
                weekly("11564", 2026, 6, 23.8, 23.8, 23.8, pass_yd=250.0, pass_td=2.0),
                weekly("11564", 2026, 7, 17.96, 17.96, 17.96, opp="CHI", pass_yd=169.0),
            ]
        )
        if with_espn_cache:
            await cache.set(
                session,
                "espn",
                ROSTER_MATCHUP_ENDPOINT,
                EspnClient._cache_params(1, 2026, roster_matchup_params(7)),
                json.dumps(espn_roster_payload(4431452, 7)),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        await session.commit()


async def test_envelope_game_log_and_season_summaries(client, db):
    await seed(db)
    response = await client.get(
        "/api/players/espn:p-4431452/stats", params={"team_id": "espn:l-1-t-1"}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"].startswith("private, max-age=15")
    body = response.json()
    assert set(body) == {"data", "meta"}
    data = body["data"]

    assert data["position_group"] == "QB"
    assert data["points_format"] == "half_ppr"
    assert data["points_format_fallback"] is False
    assert [c["key"] for c in data["columns"]][:3] == ["pass_cmp", "pass_att", "pass_yd"]
    assert [(r["season"], r["week"]) for r in data["game_log"]] == [
        (2026, 6),
        (2026, 7),
        (2025, 1),
        (2025, 2),
    ]
    seasons = {s["season"]: s for s in data["seasons"]}
    assert list(seasons) == [2026, 2025]
    assert seasons[2025]["games"] == 2
    assert seasons[2025]["fantasy_points"] == 43.1
    assert seasons[2025]["ppg"] == 21.55
    assert seasons[2025]["stats"]["pass_yd"] == 587.0


async def test_this_week_uses_espn_league_scoring_and_opponents_slot(client, db):
    await seed(db)
    data = (
        await client.get(
            "/api/players/espn:p-4431452/stats",
            params={"team_id": "espn:l-1-t-1", "week": 7},
        )
    ).json()["data"]
    week = data["this_week"]
    assert week["week"] == 7 and week["final"] is False
    assert week["league_points"] == 10.32
    assert week["league_proj"] == 20.6
    assert week["is_live"] is True and week["status_text"] == "Q3 4:12"
    assert week["stats_source"] == "espn"
    assert week["stats"]["pass_yd"] == 103.0 and week["stats"]["rush_td"] == 1.0
    assert week["breakdown_source"] == "league"
    # Zero-point stats dropped; sorted by size; sums to ESPN's own total exactly.
    assert [line["label"] for line in week["breakdown"]] == [
        "Rushing TD",
        "Passing yards",
        "Rushing yards",
        "Interceptions thrown",
    ]
    assert week["breakdown_total"] == 10.32


async def test_in_progress_sleeper_breakdown_is_not_reconciled(client, db):
    """Mid-week the league score and Sleeper's line lag each other; the gap is not a
    scoring rule and must not be presented as one."""
    await seed(db, with_espn_cache=False)
    data = (
        await client.get(
            "/api/players/espn:p-4431452/stats",
            params={"team_id": "espn:l-1-t-1", "week": 7},
        )
    ).json()["data"]
    week = data["this_week"]
    assert week["stats_source"] == "sleeper"
    assert week["breakdown_source"] == "estimated"
    labels = {line["label"]: line["points"] for line in week["breakdown"]}
    assert labels == {"Passing yards": 6.76}
    assert week["breakdown_total"] == 6.76
    assert week["league_points"] == 10.32


async def test_final_week_sleeper_breakdown_reconciles_to_league_total(client, db):
    await seed(db, with_espn_cache=False)
    async with db() as session:
        session.add(
            RosterSlot(
                team_id="espn:l-1-t-1",
                week=6,
                slot="QB",
                player_id="espn:p-4431452",
                proj_points=19.0,
                actual_points=25.0,
            )
        )
        await session.commit()
    data = (
        await client.get(
            "/api/players/espn:p-4431452/stats",
            params={"team_id": "espn:l-1-t-1", "week": 6},
        )
    ).json()["data"]
    week = data["this_week"]
    assert week["final"] is True
    labels = {line["label"]: line["points"] for line in week["breakdown"]}
    # 250 yds (10) + 2 TD (8) = 18, reconciled to the league's 25.
    assert labels["Passing yards"] == 10.0
    assert labels[player_stats.RECONCILE_LABEL] == 7.0
    assert week["breakdown_total"] == 25.0


async def test_unmatched_player_has_empty_history(client, db):
    await seed(db)
    data = (await client.get("/api/players/yahoo:470.p.1/stats")).json()["data"]
    assert data["sleeper_id"] is None
    assert data["game_log"] == [] and data["seasons"] == []
    assert data["this_week"]["breakdown"] == []
    # No viewing team: PPR, and not flagged as a fallback from a custom league.
    assert data["points_format"] == "ppr" and data["points_format_fallback"] is False


async def test_custom_scoring_falls_back_to_ppr_and_says_so(client, db):
    await seed(db, scoring="custom")
    data = (
        await client.get("/api/players/espn:p-4431452/stats", params={"team_id": "espn:l-1-t-1"})
    ).json()["data"]
    assert data["points_format"] == "ppr"
    assert data["points_format_fallback"] is True


async def test_unknown_player_is_a_typed_404(client, db):
    await seed(db)
    response = await client.get("/api/players/espn:p-1/stats")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "player_not_found"


# ---- season game log (Game Log tab) --------------------------------------------------

# NE's 2026 slate as far as these tests need it: a bye in week 5, the live week 7 at home
# to CHI, and BUF playing KC in week 8 for the traded-player case.
SCHEDULE_2026 = [
    {"week": 1, "home": "NE", "away": "BUF", "date": "2026-09-13"},
    {"week": 2, "home": "MIA", "away": "NE", "date": "2026-09-20"},
    {"week": 3, "home": "NE", "away": "NYJ", "date": "2026-09-27"},
    {"week": 4, "home": "PIT", "away": "NE", "date": "2026-10-04"},
    {"week": 5, "home": "MIA", "away": "BUF", "date": "2026-10-11"},
    {"week": 6, "home": "NYJ", "away": "NE", "date": "2026-10-11"},
    {"week": 7, "home": "NE", "away": "CHI", "date": "2026-10-18"},
    {"week": 8, "home": "MIA", "away": "NE", "date": "2026-10-25"},
    {"week": 8, "home": "BUF", "away": "KC", "date": "2026-10-25"},
    {"week": 9, "home": "NE", "away": "BUF", "date": "2026-11-01"},
]


async def seed_season_context(db, *, game_state="in", ranks=True) -> None:
    far = datetime.now(UTC) + timedelta(hours=12)
    async with db() as session:
        await cache.set(
            session, "sleeper", "schedule", {"season": 2026}, json.dumps(SCHEDULE_2026), far
        )
        if ranks:
            blob = {
                "season": 2026,
                "through_week": 6,
                "teams": 32,
                "dvp": {"QB": {"half_ppr": {"NYJ": 30, "CHI": 12, "MIA": 3, "BUF": 18}}},
                "pos_rank": {"half_ppr": {"11564": 9}},
                "numbers": {"11564": "10"},
            }
            await cache.set(
                session, "gridiron", "matchup_ranks", {"season": 2026}, json.dumps(blob), far
            )
        session.add(
            LiveNflGame(
                nfl_game_id="401",
                home_team="NE",
                away_team="CHI",
                home_score=7,
                away_score=3,
                state=game_state,
                kickoff_at=datetime(2026, 10, 18, 17, 0),
            )
        )
        for week, pts in [(6, 19.5), (7, 21.0), (8, 17.25)]:
            session.add(
                PlayerProjection(
                    player_id="espn:p-4431452",
                    season=2026,
                    week=week,
                    source="rotowire",
                    pts_ppr=pts + 1,
                    pts_half_ppr=pts,
                    pts_std=pts - 1,
                    match_tier="id",
                    fetched_at=FETCHED_AT,
                )
            )
        # Season-long scope (week 0) must not leak into the weekly column.
        session.add(
            PlayerProjection(
                player_id="espn:p-4431452",
                season=2026,
                week=0,
                source="rotowire",
                pts_half_ppr=300.0,
                match_tier="id",
                fetched_at=FETCHED_AT,
            )
        )
        await session.commit()


async def _season_log(client, **params):
    response = await client.get(
        "/api/players/espn:p-4431452/stats", params={"team_id": "espn:l-1-t-1", **params}
    )
    return response.json()["data"]


async def test_season_log_covers_every_week_with_matchup_context(client, db):
    await seed(db)
    await seed_season_context(db)
    data = await _season_log(client)
    log = data["season_log"]

    assert log["season"] == 2026
    assert [c["key"] for c in log["columns"]] == [
        "pass_yd",
        "pass_td",
        "pass_int",
        "rush_yd",
        "rush_td",
    ]
    assert next(c for c in log["columns"] if c["key"] == "pass_int")["lower_is_better"] is True
    assert log["fantasy_points"] == round(23.8 + 17.96, 2)
    assert log["position_rank"] == 9
    assert log["bye_week"] == 5
    assert log["ranked_teams"] == 32 and log["ranks_through_week"] == 6
    assert data["jersey_number"] == "10"

    weeks = {w["week"]: w for w in log["weeks"]}
    assert list(weeks) == list(range(1, 10))
    assert {w: weeks[w]["state"] for w in weeks} == {
        1: "dnp",
        2: "dnp",
        3: "dnp",
        4: "dnp",
        5: "bye",
        6: "final",
        7: "live",
        8: "upcoming",
        9: "upcoming",
    }
    assert weeks[5]["opponent"] is None and weeks[5]["home"] is None

    six = weeks[6]
    assert (six["opponent"], six["home"], six["opponent_rank"]) == ("NYJ", False, 30)
    assert six["fantasy_points"] == 23.8 and six["proj_points"] == 19.5
    # Zeros Sleeper leaves out come back as 0 in a game played.
    assert six["stats"] == {
        "pass_yd": 250.0,
        "pass_td": 2.0,
        "pass_int": 0.0,
        "rush_yd": 0.0,
        "rush_td": 0.0,
    }

    seven = weeks[7]
    assert (seven["opponent"], seven["home"], seven["opponent_rank"]) == ("CHI", True, 12)

    eight = weeks[8]
    assert (eight["opponent"], eight["home"], eight["opponent_rank"]) == ("MIA", False, 3)
    assert eight["proj_points"] == 17.25
    assert eight["fantasy_points"] is None and eight["stats"] is None


async def test_live_week_turns_final_once_his_game_is_over(client, db):
    await seed(db)
    await seed_season_context(db, game_state="post")
    weeks = {w["week"]: w for w in (await _season_log(client))["season_log"]["weeks"]}
    assert weeks[7]["state"] == "final"


async def test_season_log_without_ranks_or_schedule_still_lists_played_weeks(client, db):
    await seed(db)
    data = await _season_log(client)
    log = data["season_log"]
    assert log["ranked_teams"] == 0 and log["position_rank"] is None and log["bye_week"] is None
    assert data["jersey_number"] is None
    weeks = {w["week"]: w for w in log["weeks"]}
    assert len(weeks) == player_stats.REGULAR_SEASON_WEEKS
    assert weeks[6]["state"] == "final" and weeks[6]["opponent"] == "NYJ"
    assert weeks[6]["home"] is None and weeks[6]["opponent_rank"] is None
    # No schedule: a past week with no line can't be told from a bye.
    assert weeks[5]["state"] == "dnp"
    assert weeks[10]["state"] == "upcoming"


async def test_traded_player_keeps_his_old_matchups_and_takes_his_new_teams_schedule(client, db):
    await seed(db)
    await seed_season_context(db)
    async with db() as session:
        player = await session.get(Player, "espn:p-4431452")
        player.nfl_team = "BUF"
        await session.commit()
    weeks = {w["week"]: w for w in (await _season_log(client))["season_log"]["weeks"]}
    assert (weeks[6]["opponent"], weeks[6]["home"]) == ("NYJ", False)
    assert (weeks[8]["opponent"], weeks[8]["home"], weeks[8]["opponent_rank"]) == (
        "KC",
        True,
        None,
    )


async def test_free_agent_with_nothing_on_file_has_no_season_log(client, db):
    await seed(db)
    await seed_season_context(db)
    data = (await client.get("/api/players/yahoo:470.p.1/stats")).json()["data"]
    assert data["season_log"] is None


def test_week_state_rules():
    state = player_stats._week_state
    assert state(has_line=True, scheduled=True, week=3, live_week=7, game_state=None) == "final"
    assert state(has_line=True, scheduled=True, week=7, live_week=7, game_state=None) == "live"
    assert state(has_line=False, scheduled=False, week=9, live_week=7, game_state=None) == "bye"
    assert state(has_line=False, scheduled=True, week=7, live_week=7, game_state="pre") == (
        "upcoming"
    )
    assert state(has_line=False, scheduled=True, week=7, live_week=7, game_state="in") == "live"
    assert state(has_line=False, scheduled=True, week=7, live_week=7, game_state="post") == "dnp"
    assert state(has_line=False, scheduled=None, week=3, live_week=7, game_state=None) == "dnp"


# ---- pure helpers ---------------------------------------------------------------------


def test_estimate_breakdown_reception_points_follow_format():
    stats = {"rec": 8.0, "rec_yd": 61.0, "rush_yd": 30.0}
    ppr = player_stats.estimate_breakdown(stats, "RB", "ppr", None)
    std = player_stats.estimate_breakdown(stats, "RB", "standard", None)
    assert {line.label: line.points for line in ppr}["Receptions"] == 8.0
    assert "Receptions" not in {line.label for line in std}


def test_estimate_breakdown_dst_points_allowed_tier():
    lines = player_stats.estimate_breakdown(
        {"sack": 6.0, "int": 1.0, "pts_allow": 7.0}, "DST", "ppr", 15.0
    )
    by_label = {line.label: line for line in lines}
    assert by_label["Sacks"].points == 6.0
    assert by_label["7-13 points allowed"].points == 4.0
    assert by_label["7-13 points allowed"].stat_value is None
    assert sum(line.points for line in lines) == 15.0


def test_estimate_breakdown_omits_reconcile_line_when_it_adds_up():
    lines = player_stats.estimate_breakdown({"pass_yd": 250.0, "pass_td": 2.0}, "QB", "ppr", 18.0)
    assert player_stats.RECONCILE_LABEL not in {line.label for line in lines}


def test_summarize_seasons_uses_max_for_long_field_goal():
    columns = player_stats.COLUMNS["K"]
    rows = [
        GameLogRow(
            season=2025,
            week=w,
            date=None,
            team="LV",
            opponent=None,
            fantasy_points=pts,
            stats={"fgm": fgm, "fgm_lng": lng},
        )
        for w, pts, fgm, lng in [(1, 7.0, 2.0, 48.0), (2, 3.0, 1.0, 52.0)]
    ]
    (summary,) = player_stats.summarize_seasons(rows, columns)
    assert summary.stats == {"fgm": 3.0, "fgm_lng": 52.0}
    assert summary.ppg == 5.0
