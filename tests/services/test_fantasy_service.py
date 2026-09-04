"""`services/fantasy_service.py` — read paths against a seeded temp DB (reads never fetch
upstream, so no platform mocking there) and `refresh_discovery` against respx-mocked
platform HTTP using the captured fixtures."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import respx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.config import Settings
from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    Connection,
    Headshot,
    League,
    LiveNflGame,
    Matchup,
    MatchupSlot,
    Player,
    PlayerPoolEntry,
    PlayerProjection,
    RosterSlot,
    SeasonWeek,
    Team,
)
from backend.gridiron.platforms.yahoo.client import BASE_URL as YAHOO_BASE
from backend.gridiron.services import cache as cache_service
from backend.gridiron.services import credentials, differ, events, fantasy_service, live_state

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TEST_SECRET = "test-secret-key"
ESPN_BASE = "https://lm-api-reads.fantasy.espn.com"

LEAGUE_ID = "yahoo:461.l.123456"
USER_TEAM = "yahoo:461.l.123456.t.1"
OPP_TEAM = "yahoo:461.l.123456.t.2"


def load_fixture(platform: str, name: str) -> dict:
    return json.loads((FIXTURES / platform / name).read_text())


def make_settings() -> Settings:
    return Settings(
        gridiron_secret_key=TEST_SECRET,
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        espn_base_url=ESPN_BASE,
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
    engine = make_engine(tmp_path / "fantasy.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _player(pid: str, name: str, position: str = "QB", platform: str = "yahoo") -> Player:
    return Player(
        id=pid,
        platform=platform,
        platform_id=pid.split(":", 1)[1],
        name=name,
        position=position,
        nfl_team="KC",
        nfl_opponent=None,
        nfl_game_id=None,
        bye_week=6,
        injury_status="ACTIVE",
    )


async def seed_read_model(session_factory) -> None:
    """Insert normalized rows directly — the read paths are pure DB assembly."""
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456",
                name="The League of Extraordinary Gentlemen",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=14,
            )
        )
        session.add(
            Team(
                id=USER_TEAM,
                league_id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456.t.1",
                name="Gridiron Gurus",
                manager_name="Nick",
                record_w=8,
                record_l=5,
                record_t=0,
                rank_current=2,
                rank_total=10,
                points_for=1401.2,
                points_against=1322.8,
                is_user_team=True,
            )
        )
        session.add(
            Team(
                id=OPP_TEAM,
                league_id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456.t.2",
                name="The Contenders",
                manager_name="Sam",
                record_w=7,
                record_l=6,
                record_t=0,
                rank_current=4,
                rank_total=10,
                points_for=1350.0,
                points_against=1360.0,
                is_user_team=False,
            )
        )
        session.add_all(
            [
                _player("yahoo:461.p.1", "Patrick Mahomes", "QB"),
                _player("yahoo:461.p.2", "Christian McCaffrey", "RB"),
                _player("yahoo:461.p.3", "Jordan Love", "QB"),
                _player("yahoo:461.p.4", "Josh Allen", "QB"),
                _player("yahoo:461.p.5", "Bijan Robinson", "RB"),
            ]
        )
        session.add_all(
            [
                RosterSlot(
                    team_id=USER_TEAM,
                    week=14,
                    slot="QB",
                    player_id="yahoo:461.p.1",
                    proj_points=22.1,
                    actual_points=27.4,
                ),
                RosterSlot(
                    team_id=USER_TEAM,
                    week=14,
                    slot="RB1",
                    player_id="yahoo:461.p.2",
                    proj_points=18.0,
                    actual_points=12.3,
                ),
                RosterSlot(
                    team_id=USER_TEAM,
                    week=14,
                    slot="BN",
                    player_id="yahoo:461.p.3",
                    proj_points=15.0,
                    actual_points=0.0,
                ),
                RosterSlot(
                    team_id=OPP_TEAM,
                    week=14,
                    slot="QB",
                    player_id="yahoo:461.p.4",
                    proj_points=21.0,
                    actual_points=24.5,
                    game_state="post",
                ),
                RosterSlot(
                    team_id=OPP_TEAM,
                    week=14,
                    slot="RB1",
                    player_id="yahoo:461.p.5",
                    proj_points=16.0,
                    actual_points=9.9,
                ),
            ]
        )
        # Historical starts for most_started: Mahomes started weeks 9-13 too.
        for week in range(9, 14):
            session.add(
                RosterSlot(
                    team_id=USER_TEAM,
                    week=week,
                    slot="QB",
                    player_id="yahoo:461.p.1",
                    proj_points=20.0,
                    actual_points=20.0 + week,
                )
            )
        matchup = Matchup(
            id="yahoo:461.l.123456.mu.14",
            league_id=LEAGUE_ID,
            week=14,
            home_team_id=USER_TEAM,
            away_team_id=OPP_TEAM,
            home_score=88.24,
            away_score=76.10,
            home_proj=104.5,
            away_proj=95.2,
            is_complete=False,
        )
        session.add(matchup)
        session.add(
            MatchupSlot(
                matchup_id=matchup.id,
                slot="QB",
                home_player_id="yahoo:461.p.1",
                away_player_id="yahoo:461.p.4",
                home_pts=27.4,
                away_pts=24.5,
            )
        )
        scores = [(9, 101.2, 95.0, True), (10, 88.0, 90.1, False), (11, 132.6, 104.0, True)]
        scores += [(12, 111.0, 99.5, True), (13, 92.4, 80.2, True), (14, 88.24, 76.1, False)]
        for week, score, opp, win in scores:
            session.add(
                SeasonWeek(
                    team_id=USER_TEAM,
                    week=week,
                    score=score,
                    opp_score=opp,
                    opp_team_name="The Contenders",
                    is_win=win,
                    is_current=week == 14,
                )
            )
        await session.commit()


# --- reads ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_teams_returns_user_teams_with_overlays(session_factory) -> None:
    await seed_read_model(session_factory)

    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert len(teams) == 1
    team = teams[0]
    assert team.id == USER_TEAM
    assert team.is_user_team is True
    assert team.record.w == 8 and team.record.l == 5 and team.record.t == 0
    assert team.rank.current == 2 and team.rank.total == 10
    assert team.current_score == 88.24
    assert team.current_opp_score == 76.10
    assert team.current_opponent_name == "The Contenders"
    assert team.spark_last_6 == [101.2, 88.0, 132.6, 111.0, 92.4, 88.24]
    assert team.accent_color == "#FF2D55"


@pytest.mark.asyncio
async def test_list_teams_empty_db_returns_empty_list(session_factory) -> None:
    async with session_factory() as session:
        assert await fantasy_service.list_teams(session, week=1) == []


@pytest.mark.asyncio
async def test_list_teams_excludes_teams_in_disabled_leagues(session_factory) -> None:
    """Settings' "ESPN Leagues" card (task 7.3): disabling a league hides its teams from
    the aggregation without deleting the underlying league/team rows."""
    await seed_read_model(session_factory)
    disabled_league_id = "espn:9999999"
    disabled_team_id = "espn:l-9999999-t-1"
    async with session_factory() as session:
        session.add(
            League(
                id=disabled_league_id,
                platform="espn",
                platform_id="9999999",
                name="Disabled League",
                season=2025,
                team_count=8,
                scoring_type="standard",
                current_week=14,
                is_enabled=False,
            )
        )
        session.add(
            Team(
                id=disabled_team_id,
                league_id=disabled_league_id,
                platform="espn",
                platform_id="9999999-t-1",
                name="Should Not Appear",
                manager_name="Nobody",
                record_w=0,
                record_l=0,
                record_t=0,
                rank_current=1,
                rank_total=8,
                points_for=0.0,
                points_against=0.0,
                is_user_team=True,
            )
        )
        await session.commit()

    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert disabled_team_id not in {t.id for t in teams}
    assert USER_TEAM in {t.id for t in teams}


@pytest.mark.asyncio
async def test_list_teams_is_live_true_when_a_starter_nfl_team_is_in_progress(
    session_factory,
) -> None:
    """P8-leftover: `is_live` is computed from real `live_nfl_games` rows, not
    hardcoded. Mahomes (QB starter, nfl_team="KC") is on a team with an in-progress
    game -> the team is live."""
    await seed_read_model(session_factory)
    async with session_factory() as session:
        session.add(
            LiveNflGame(
                nfl_game_id="401",
                home_team="KC",
                away_team="LAC",
                home_score=14,
                away_score=7,
                state="in",
                clock="8:12",
                period=2,
                kickoff_at=datetime(2025, 12, 7, 18, 0, 0),
            )
        )
        await session.commit()

    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert teams[0].is_live is True


@pytest.mark.asyncio
async def test_list_teams_is_live_false_when_no_game_in_progress(session_factory) -> None:
    await seed_read_model(session_factory)
    async with session_factory() as session:
        session.add(
            LiveNflGame(
                nfl_game_id="401",
                home_team="KC",
                away_team="LAC",
                home_score=0,
                away_score=0,
                state="pre",
                clock=None,
                period=None,
                kickoff_at=datetime(2025, 12, 7, 18, 0, 0),
            )
        )
        await session.commit()

    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert teams[0].is_live is False


@pytest.mark.asyncio
async def test_list_teams_is_live_false_when_only_a_bench_player_is_in_progress(
    session_factory,
) -> None:
    """Bench/IR slots don't count — mirrors STARTER_EXCLUDED_SLOTS everywhere else. The
    seeded bench player (Jordan Love, "yahoo:461.p.3") has no nfl_team override so this
    reuses the default "KC" from `_player()`; give the *opponent's* live game a team no
    one on the user's starters plays for, and confirm the user's team stays not-live even
    though its own bench player's team ("KC") is technically live -- since Mahomes (a
    starter) is ALSO on "KC" this scenario can't isolate bench-only, so instead this
    seeds a distinct bench-only nfl_team via a fresh player/slot swap."""
    await seed_read_model(session_factory)
    async with session_factory() as session:
        # Swap the bench player (yahoo:461.p.3, currently slot="BN") onto a distinct NFL
        # team no starter is on, then mark that team's game live.
        bench_player = await session.get(Player, "yahoo:461.p.3")
        bench_player.nfl_team = "DAL"
        session.add(
            LiveNflGame(
                nfl_game_id="402",
                home_team="DAL",
                away_team="PHI",
                home_score=3,
                away_score=0,
                state="in",
                clock="14:50",
                period=1,
                kickoff_at=datetime(2025, 12, 7, 13, 0, 0),
            )
        )
        await session.commit()

    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert teams[0].is_live is False


@pytest.mark.asyncio
async def test_list_teams_is_live_false_when_live_nfl_games_never_polled(session_factory) -> None:
    """No live_nfl_games rows at all (scheduler never ticked, or off-season) degrades
    every team to not-live without needing to know anything about the roster."""
    await seed_read_model(session_factory)
    async with session_factory() as session:
        teams = await fantasy_service.list_teams(session, week=14)

    assert teams[0].is_live is False


@pytest.mark.asyncio
async def test_day_rings_all_empty_when_live_nfl_games_never_polled(session_factory) -> None:
    """Task 10.6: the day-letter skeleton is always real (today's actual Thu-Mon NFL
    week), but every ring degrades to 0 when there's no live_nfl_games data to attribute
    points to a day."""
    await seed_read_model(session_factory)

    async with session_factory() as session:
        result = await fantasy_service.day_rings(session, week=14, today=date(2025, 12, 7))

    assert [d.letter for d in result.days] == ["T", "F", "S", "S", "M"]
    assert result.today_index == 3  # Sunday, Dec 7
    for day in result.days:
        assert len(day.rings) == 1  # one ring per user team (one seeded)
        assert day.rings[0].value == 0.0


@pytest.mark.asyncio
async def test_day_rings_attributes_points_to_the_games_calendar_day(session_factory) -> None:
    await seed_read_model(session_factory)
    async with session_factory() as session:
        session.add(
            LiveNflGame(
                nfl_game_id="401",
                home_team="KC",
                away_team="LAC",
                home_score=14,
                away_score=7,
                state="post",
                clock=None,
                period=None,
                kickoff_at=datetime(2025, 12, 7, 18, 0, 0),  # Sunday, day_span index 3
            )
        )
        await session.commit()

    async with session_factory() as session:
        result = await fantasy_service.day_rings(session, week=14, today=date(2025, 12, 7))

    # Every seeded USER_TEAM starter (_player() hardcodes nfl_team="KC") played on
    # Sunday -> all of the team's week-14 points land on the Sunday ring.
    assert result.days[3].letter == "S"
    assert result.days[3].rings[0].value == pytest.approx(1.0)
    for i in (0, 1, 2, 4):
        assert result.days[i].rings[0].value == 0.0


@pytest.mark.asyncio
async def test_day_rings_today_index_is_none_outside_the_game_day_span(session_factory) -> None:
    await seed_read_model(session_factory)

    async with session_factory() as session:
        result = await fantasy_service.day_rings(session, week=14, today=date(2025, 12, 9))  # Tue

    assert result.today_index is None


@pytest.mark.asyncio
async def test_get_team_splits_starters_and_bench_and_includes_history(session_factory) -> None:
    await seed_read_model(session_factory)

    async with session_factory() as session:
        detail = await fantasy_service.get_team(session, USER_TEAM, week=14)

    assert detail is not None
    assert detail.team.id == USER_TEAM
    assert detail.league.id == LEAGUE_ID
    assert [s.slot for s in detail.starters] == ["QB", "RB1"]
    assert [s.slot for s in detail.bench] == ["BN"]
    assert detail.starters[0].player.name == "Patrick Mahomes"
    assert detail.starters[0].player.headshot_url == "/api/headshots/yahoo/1.png"
    assert [w.week for w in detail.record_history] == [9, 10, 11, 12, 13, 14]


@pytest.mark.asyncio
async def test_get_team_unknown_id_returns_none(session_factory) -> None:
    await seed_read_model(session_factory)
    async with session_factory() as session:
        assert await fantasy_service.get_team(session, "yahoo:nope", week=14) is None


@pytest.mark.asyncio
async def test_get_h2h_returns_matchup_slots_and_remaining(session_factory) -> None:
    await seed_read_model(session_factory)

    async with session_factory() as session:
        h2h = await fantasy_service.get_h2h(session, USER_TEAM, week=14)

    assert h2h is not None
    assert h2h.matchup.id == "yahoo:461.l.123456.mu.14"
    assert h2h.matchup.home_score == 88.24
    assert len(h2h.slots) == 1
    assert h2h.slots[0].slot == "QB"
    assert h2h.slots[0].home_player.name == "Patrick Mahomes"
    assert h2h.slots[0].away_player.name == "Josh Allen"
    # Mine: QB + RB1, neither game_state == "post". Theirs: QB is post, RB1 still live.
    assert h2h.remaining.mine == 2
    assert h2h.remaining.theirs == 1


@pytest.mark.asyncio
async def test_get_h2h_no_matchup_returns_none(session_factory) -> None:
    await seed_read_model(session_factory)
    async with session_factory() as session:
        assert await fantasy_service.get_h2h(session, USER_TEAM, week=3) is None


@pytest.mark.asyncio
async def test_get_season_computes_highlights(session_factory) -> None:
    await seed_read_model(session_factory)

    async with session_factory() as session:
        season = await fantasy_service.get_season(session, USER_TEAM)

    assert season is not None
    assert [w.week for w in season.weeks] == [9, 10, 11, 12, 13, 14]
    assert season.highlights.season_high is not None
    assert season.highlights.season_high.week == 11
    assert season.highlights.season_high.score == 132.6
    assert season.highlights.win_streak == 3  # weeks 11-13
    most = season.highlights.most_started
    assert most is not None
    assert most.player.name == "Patrick Mahomes"
    assert most.starts == 6
    # (29 + 30 + 31 + 32 + 33 + 27.4) / 6
    assert most.avg_points == pytest.approx(30.4, abs=0.01)


@pytest.mark.asyncio
async def test_get_season_unknown_team_returns_none(session_factory) -> None:
    async with session_factory() as session:
        assert await fantasy_service.get_season(session, "yahoo:nope") is None


@pytest.mark.asyncio
async def test_current_week_defaults_from_league_rows(session_factory) -> None:
    async with session_factory() as session:
        assert await fantasy_service.current_week(session) == 1  # empty DB fallback
    await seed_read_model(session_factory)
    async with session_factory() as session:
        assert await fantasy_service.current_week(session) == 14


@pytest.mark.asyncio
async def test_build_meta_reports_disconnected_platforms_and_as_of(session_factory) -> None:
    fetched_at = datetime(2026, 7, 1, 12, 0, 0)
    async with session_factory() as session:
        await cache_service.set(
            session,
            "yahoo",
            "roster",
            None,
            "{}",
            expires_at=fetched_at + timedelta(hours=1),
            fetched_at=fetched_at,
        )

    async with session_factory() as session:
        meta = await fantasy_service.build_meta(session)

    assert meta.live_state == "off_day"
    assert meta.as_of == fetched_at
    assert meta.platforms["yahoo"].ok is False
    assert meta.platforms["yahoo"].error == "not_connected"
    assert meta.platforms["espn"].ok is False
    assert meta.next_refresh_at is not None


@pytest.mark.asyncio
async def test_build_meta_reports_last_refresh_error_for_connected_platform(
    session_factory,
) -> None:
    async with session_factory() as session:
        session.add(
            Connection(
                platform="espn",
                swid_enc=credentials.encrypt(TEST_SECRET, "{ABC-123}"),
                espn_s2_enc=credentials.encrypt(TEST_SECRET, "s2"),
            )
        )
        await session.commit()
    fantasy_service._LAST_ERRORS["espn"] = "auth_required"

    async with session_factory() as session:
        meta = await fantasy_service.build_meta(session)

    assert meta.platforms["espn"].ok is False
    assert meta.platforms["espn"].error == "auth_required"


# --- refresh_discovery ---------------------------------------------------------------


def _single_league_yahoo_leagues() -> dict:
    """Trim the leagues fixture to the first league so discovery only fans out once."""
    raw = load_fixture("yahoo", "leagues.json")
    leagues = raw["fantasy_content"]["users"]["0"]["user"][1]["games"]["0"]["game"][1]["leagues"]
    del leagues["1"]
    leagues["count"] = 1
    return raw


def _mock_yahoo_discovery() -> None:
    roster = load_fixture("yahoo", "roster.json")
    opp_roster = json.loads(json.dumps(roster).replace(".t.1", ".t.2"))
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_codes=nfl").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "games.json"))
    )
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_keys=461/leagues").mock(
        return_value=httpx.Response(200, json=_single_league_yahoo_leagues())
    )
    respx.get(f"{YAHOO_BASE}/league/461.l.123456/teams").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "teams.json"))
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.1/roster;week=14/players/stats").mock(
        return_value=httpx.Response(200, json=roster)
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.1/matchups;weeks=14").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "matchup.json"))
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.2/roster;week=14/players/stats").mock(
        return_value=httpx.Response(200, json=opp_roster)
    )


async def _connect_yahoo(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            Connection(
                platform="yahoo",
                access_token_enc=credentials.encrypt(TEST_SECRET, "at"),
                refresh_token_enc=credentials.encrypt(TEST_SECRET, "rt"),
            )
        )
        await session.commit()


ESPN_SWID = "{ABC12345-DEAD-BEEF-0000-111111111111}"


async def _connect_espn(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            Connection(
                platform="espn",
                swid_enc=credentials.encrypt(TEST_SECRET, ESPN_SWID),
                espn_s2_enc=credentials.encrypt(TEST_SECRET, "s2-value"),
            )
        )
        session.add(
            League(
                id="espn:1234567",
                platform="espn",
                platform_id="1234567",
                name="Highland Bombers League",
                season=2024,
                team_count=10,
                scoring_type="ppr",
                current_week=9,
            )
        )
        await session.commit()


def _mock_espn_discovery() -> None:
    league_path = f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1234567"
    # Roster route first — respx matches routes in registration order and the league
    # route below (no params constraint) would otherwise swallow the roster call.
    respx.get(league_path, params={"scoringPeriodId": "10"}).mock(
        return_value=httpx.Response(200, json=load_fixture("espn", "roster_matchup.json"))
    )
    respx.get(league_path).mock(
        return_value=httpx.Response(200, json=load_fixture("espn", "league.json"))
    )
    probe_year = fantasy_service._current_season()
    respx.get(f"https://fan.api.espn.com/apis/v2/fans/{quote(ESPN_SWID, safe='')}").mock(
        return_value=httpx.Response(
            200,
            json={
                "preferences": [
                    {
                        "id": f"12:1234567:1:{probe_year}",
                        "typeId": 9,
                        "metaData": {
                            "entry": {
                                "abbrev": "FFL",
                                "entryId": 12,
                                "gameId": 1,
                                "seasonId": probe_year,
                            }
                        },
                    }
                ]
            },
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_yahoo_persists_normalized_rows(session_factory) -> None:
    await _connect_yahoo(session_factory)
    _mock_yahoo_discovery()

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is True

    async with session_factory() as session:
        league = await session.get(League, LEAGUE_ID)
        assert league is not None
        assert league.current_week == 14
        assert league.season == 2025

        teams = (await session.execute(select(Team))).scalars().all()
        assert {t.id for t in teams} == {USER_TEAM, OPP_TEAM}
        user_team = next(t for t in teams if t.id == USER_TEAM)
        assert user_team.is_user_team is True
        assert user_team.manager_name == "Nick"
        assert user_team.rank_total == 2  # overlaid from discovered team count

        user_slots = (
            (await session.execute(select(RosterSlot).where(RosterSlot.team_id == USER_TEAM)))
            .scalars()
            .all()
        )
        assert len(user_slots) == 11

        matchup = await session.get(Matchup, "yahoo:461.l.123456.mu.14")
        assert matchup is not None
        assert matchup.home_score == 88.24
        assert matchup.is_complete is False

        mslots = (
            (await session.execute(select(MatchupSlot).where(MatchupSlot.matchup_id == matchup.id)))
            .scalars()
            .all()
        )
        assert len(mslots) == 9  # all starter slots paired (BN/IR excluded)

        weeks = (await session.execute(select(SeasonWeek))).scalars().all()
        assert {(w.team_id, w.week) for w in weeks} == {(USER_TEAM, 14), (OPP_TEAM, 14)}
        assert all(w.is_current for w in weeks)
        assert all(not w.is_win for w in weeks)  # midevent matchup isn't complete

        # Yahoo headshot source URLs stashed for services/headshots.py.
        headshot = await session.get(Headshot, ("yahoo", "30123"))
        assert headshot is not None
        assert headshot.source_url.startswith("https://")


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_espn_persists_normalized_rows(session_factory) -> None:
    await _connect_espn(session_factory)
    _mock_espn_discovery()

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["espn"].ok is True

    async with session_factory() as session:
        league = await session.get(League, "espn:1234567")
        assert league is not None
        assert league.current_week == 10  # refreshed from upstream (was seeded as 9)

        user_team = await session.get(Team, "espn:l-1234567-t-2")
        assert user_team is not None
        assert user_team.is_user_team is True
        assert user_team.manager_name == "Nick B"
        assert user_team.rank_total == 10

        players = (
            (await session.execute(select(Player).where(Player.platform == "espn"))).scalars().all()
        )
        assert players
        assert all(not p.platform_id.startswith("p-") for p in players)

        home_slots = (
            (
                await session.execute(
                    select(RosterSlot).where(RosterSlot.team_id == "espn:l-1234567-t-2")
                )
            )
            .scalars()
            .all()
        )
        assert len(home_slots) == 13

        matchup = await session.get(Matchup, "espn:l-1234567-m-5001-w-10")
        assert matchup is not None
        mslots = (
            (await session.execute(select(MatchupSlot).where(MatchupSlot.matchup_id == matchup.id)))
            .scalars()
            .all()
        )
        assert mslots

        weeks = (await session.execute(select(SeasonWeek))).scalars().all()
        assert {w.team_id for w in weeks} == {"espn:l-1234567-t-2", "espn:l-1234567-t-5"}


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_isolates_platform_failures(session_factory) -> None:
    await _connect_yahoo(session_factory)
    await _connect_espn(session_factory)
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_codes=nfl").mock(
        return_value=httpx.Response(500)
    )
    _mock_espn_discovery()

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is False
    assert "upstream_error" in outcomes["yahoo"].error
    assert outcomes["espn"].ok is True

    # ESPN rows landed despite the Yahoo failure.
    async with session_factory() as session:
        assert await session.get(Team, "espn:l-1234567-t-2") is not None
        # A 5xx sets the cooldown and the error is surfaced via build_meta.
        meta = await fantasy_service.build_meta(session)
    assert meta.platforms["yahoo"].ok is False
    assert "upstream_error" in meta.platforms["yahoo"].error
    assert "yahoo" in fantasy_service._COOLDOWN_UNTIL


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_skips_platform_in_cooldown(session_factory) -> None:
    await _connect_yahoo(session_factory)
    fantasy_service.set_cooldown("yahoo")

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is False
    assert outcomes["yahoo"].error.startswith("cooldown until ")
    assert respx.calls.call_count == 0  # no upstream traffic while cooling down


@pytest.mark.asyncio
async def test_refresh_discovery_with_no_connections_is_a_clean_noop(session_factory) -> None:
    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is True
    assert outcomes["espn"].ok is True
    assert fantasy_service.summarize_outcomes(outcomes) is None


# --------------------------------------------------------------------------------------
# Phase 8: is_enabled skip (bandwidth optimization) + refresh_fantasy (task 8.3)
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_yahoo_skips_disabled_league(session_factory) -> None:
    await _connect_yahoo(session_factory)
    _mock_yahoo_discovery()
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456",
                name="Pre-existing",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=14,
                is_enabled=False,
            )
        )
        await session.commit()

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is True
    # The leagues-list call happens (needed to even know the league exists), but nothing
    # past that — no team/roster/matchup upstream traffic for the disabled league.
    assert respx.calls.call_count == 2  # games + leagues-list only


@pytest.mark.asyncio
@respx.mock
async def test_refresh_discovery_espn_skips_disabled_league(session_factory) -> None:
    await _connect_espn(session_factory)
    _mock_espn_discovery()
    async with session_factory() as session:
        league = await session.get(League, "espn:1234567")
        league.is_enabled = False
        await session.commit()

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["espn"].ok is True
    # Not even the probe-league detail fetch happens for a disabled league — only the
    # credential-probe call (mocked as an empty leagues list) goes out.
    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fantasy_publishes_data_changed_for_moved_scopes(session_factory) -> None:
    await _connect_yahoo(session_factory)
    _mock_yahoo_discovery()
    queue = events.subscribe()

    async with session_factory() as session:
        error = await fantasy_service.refresh_fantasy(session, settings=make_settings())

    assert error is None
    published = [queue.get_nowait() for _ in range(queue.qsize())]
    data_changed = [e for e in published if e.type == "data.changed"]
    assert data_changed  # first-ever run: every fingerprint is "new"
    assert "teams" in data_changed[0].scopes


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fantasy_second_run_with_no_changes_publishes_nothing(
    session_factory,
) -> None:
    await _connect_yahoo(session_factory)
    _mock_yahoo_discovery()

    async with session_factory() as session:
        await fantasy_service.refresh_fantasy(session, settings=make_settings())

    queue = events.subscribe()
    async with session_factory() as session:
        await fantasy_service.refresh_fantasy(session, settings=make_settings())

    assert queue.empty()  # nothing in the read-model actually changed the 2nd time


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fantasy_all_platforms_failing_publishes_nothing(session_factory) -> None:
    """Task 11.2: publish should only ever follow a successful write. When discovery
    fails outright there's nothing new in the DB to diff against the previous run's
    fingerprints, so nothing gets published -- verifying/locking in the existing
    behavior rather than needing a new guard."""
    await _connect_yahoo(session_factory)
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_codes=nfl").mock(
        return_value=httpx.Response(500)
    )
    queue = events.subscribe()

    async with session_factory() as session:
        error = await fantasy_service.refresh_fantasy(session, settings=make_settings())

    assert error is not None
    assert queue.empty()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fantasy_invalidates_cache_only_when_live(
    session_factory, monkeypatch
) -> None:
    await _connect_yahoo(session_factory)
    _mock_yahoo_discovery()

    calls: list[str] = []
    original_invalidate = cache_service.invalidate

    async def spy_invalidate(session, **kwargs):
        calls.append(kwargs.get("platform"))
        return await original_invalidate(session, **kwargs)

    monkeypatch.setattr(cache_service, "invalidate", spy_invalidate)

    live_state.set_current_live_state("off_day")
    async with session_factory() as session:
        await fantasy_service.refresh_fantasy(session, settings=make_settings())
    assert calls == []

    live_state.set_current_live_state("live")
    async with session_factory() as session:
        await fantasy_service.refresh_fantasy(session, settings=make_settings())
    assert set(calls) == {"yahoo", "espn"}


# ---------------------------------------------------------------------------
# refresh_player_pool (add-player-pool group 3)
# ---------------------------------------------------------------------------


def _pool_body(gibbs_season_proj: float) -> dict:
    """A two-player pool. `gibbs_season_proj` is what varies between leagues — it is
    an `appliedTotal`, i.e. a SCORED value, so a PPR and a half-PPR league genuinely
    report different numbers for the same pass-catcher."""
    return {
        "players": [
            {
                "id": 4429795,
                "status": "FREEAGENT",
                "onTeamId": 0,
                "player": {
                    "id": 4429795,
                    "fullName": "Jahmyr Gibbs",
                    "defaultPositionId": 2,
                    "proTeamId": 8,
                    "injuryStatus": "ACTIVE",
                    "byeWeek": 5,
                    "eligibleSlots": [2, 3, 23],
                    "ownership": {"percentOwned": 99.9, "percentStarted": 98.0},
                    "stats": [
                        {
                            "scoringPeriodId": 0,
                            "statSourceId": 1,
                            "statSplitTypeId": 0,
                            "seasonId": 2024,
                            "appliedTotal": gibbs_season_proj,
                        }
                    ],
                },
            },
            {
                "id": 3139477,
                "status": "ONTEAM",
                "onTeamId": 2,
                "player": {
                    "id": 3139477,
                    "fullName": "Patrick Mahomes",
                    "defaultPositionId": 1,
                    "proTeamId": 12,
                    "injuryStatus": "ACTIVE",
                    "byeWeek": 6,
                    "eligibleSlots": [0],
                    "ownership": {"percentOwned": 100.0, "percentStarted": 99.0},
                    "stats": [
                        {
                            "scoringPeriodId": 0,
                            "statSourceId": 1,
                            "statSplitTypeId": 0,
                            "seasonId": 2024,
                            "appliedTotal": 300.0,
                        }
                    ],
                },
            },
        ]
    }


async def _seed_two_espn_leagues(session_factory) -> None:
    """Two ESPN leagues with different scoring types, each with a user team."""
    async with session_factory() as session:
        session.add(
            Connection(
                platform="espn",
                swid_enc=credentials.encrypt(TEST_SECRET, ESPN_SWID),
                espn_s2_enc=credentials.encrypt(TEST_SECRET, "s2-value"),
            )
        )
        for lid, name, scoring in (
            ("1111111", "PPR League", "ppr"),
            ("2222222", "Half League", "half_ppr"),
        ):
            session.add(
                League(
                    id=f"espn:{lid}",
                    platform="espn",
                    platform_id=lid,
                    name=name,
                    season=2024,
                    team_count=10,
                    scoring_type=scoring,
                    current_week=9,
                )
            )
            session.add(
                Team(
                    id=f"espn:l-{lid}-t-2",
                    league_id=f"espn:{lid}",
                    platform="espn",
                    platform_id="2",
                    name=f"My {name} Team",
                    manager_name="Nick B",
                    record_w=5,
                    record_l=4,
                    record_t=0,
                    rank_current=3,
                    rank_total=10,
                    points_for=900.0,
                    points_against=880.0,
                    is_user_team=True,
                )
            )
        await session.commit()


def _mock_two_league_pools() -> None:
    for lid, proj in (("1111111", 364.86), ("2222222", 330.97)):
        respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/{lid}").mock(
            return_value=httpx.Response(200, json=_pool_body(proj))
        )


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_is_scoped_per_league(session_factory) -> None:
    """Design D1's regression test.

    One player, two leagues, two DIFFERENT season projections — the exact situation a
    column on `players` could not represent, since it would hold whichever league
    synced last and be wrong for the other.
    """
    await _seed_two_espn_leagues(session_factory)
    _mock_two_league_pools()

    async with session_factory() as session:
        error = await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert error is None

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(PlayerPoolEntry).where(PlayerPoolEntry.player_id == "espn:p-4429795")
                )
            )
            .scalars()
            .all()
        )
        by_league = {r.league_id: r.season_proj_points for r in rows}

    assert by_league == {
        "espn:1111111": pytest.approx(364.86),
        "espn:2222222": pytest.approx(330.97),
    }
    assert len(set(by_league.values())) == 2, "the two leagues must not collapse to one value"


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_persists_availability_and_eligibility(session_factory) -> None:
    await _seed_two_espn_leagues(session_factory)
    _mock_two_league_pools()

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())

    async with session_factory() as session:
        gibbs = await session.get(PlayerPoolEntry, ("espn:1111111", "espn:p-4429795"))
        mahomes = await session.get(PlayerPoolEntry, ("espn:1111111", "espn:p-3139477"))

        assert gibbs.status == "FREEAGENT"
        assert gibbs.on_team_id is None
        assert json.loads(gibbs.eligible_slots) == ["RB", "RB/WR", "FLEX"]

        # ONTEAM rows are ingested deliberately: they are the only source of a season
        # projection for an incumbent starter, which the waiver delta needs.
        assert mahomes.status == "ONTEAM"
        assert mahomes.on_team_id == "2"
        assert mahomes.season_proj_points == pytest.approx(300.0)

        # The player rows themselves went through the normal upsert path.
        player = await session.get(Player, "espn:p-4429795")
        assert player is not None and player.platform_id == "4429795"


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_replaces_rather_than_merges(session_factory) -> None:
    """A player claimed since the last sync must DISAPPEAR. A merge would leave the
    stale FREEAGENT row behind, offering a waiver claim on someone already rostered."""
    await _seed_two_espn_leagues(session_factory)
    _mock_two_league_pools()

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())

    respx.reset()
    # Second sync: Gibbs is gone from the pool entirely.
    shrunk = _pool_body(364.86)
    shrunk["players"] = shrunk["players"][1:]
    for lid in ("1111111", "2222222"):
        respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/{lid}").mock(
            return_value=httpx.Response(200, json=shrunk)
        )

    async with session_factory() as session:
        # Expire the 6h freshness marker the first run wrote — otherwise the second
        # call correctly no-ops (see test_refresh_player_pool_skips_a_fresh_pool).
        await cache_service.invalidate(session, platform="espn")
        await fantasy_service.refresh_player_pool(session, settings=make_settings())

    async with session_factory() as session:
        rows = (await session.execute(select(PlayerPoolEntry))).scalars().all()

    assert {r.player_id for r in rows} == {"espn:p-3139477"}


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_skips_leagues_without_a_user_team(session_factory) -> None:
    """Only leagues the user actually plays in. The ownership column is
    `is_user_team` — there is no `is_mine`."""
    await _seed_two_espn_leagues(session_factory)
    async with session_factory() as session:
        team = await session.get(Team, "espn:l-2222222-t-2")
        team.is_user_team = False
        await session.commit()

    route_1 = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1111111"
    ).mock(return_value=httpx.Response(200, json=_pool_body(364.86)))
    route_2 = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/2222222"
    ).mock(return_value=httpx.Response(200, json=_pool_body(330.97)))

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert route_1.call_count == 1
    assert route_2.call_count == 0


@pytest.mark.asyncio
async def test_refresh_player_pool_without_espn_connected_is_a_clean_noop(session_factory) -> None:
    async with session_factory() as session:
        assert await fantasy_service.refresh_player_pool(session, settings=make_settings()) is None


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_skips_a_fresh_pool(session_factory) -> None:
    """Within the 6h TTL the job is a no-op, whether triggered by the scheduler or by
    hand. The cost is the reason: each league is a ~3.7 MB pull, ~18.5 MB across five,
    so a repeated manual trigger must not re-download the universe.

    The scheduled cadence is deliberately longer than the TTL, so a scheduled run
    always finds the marker expired — this only suppresses *extra* runs.
    """
    await _seed_two_espn_leagues(session_factory)
    route = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1111111"
    ).mock(return_value=httpx.Response(200, json=_pool_body(364.86)))
    respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/2222222").mock(
        return_value=httpx.Response(200, json=_pool_body(330.97))
    )

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())
    assert route.call_count == 1

    async with session_factory() as session:
        error = await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert error is None, "a fresh pool is success, not failure"
    assert route.call_count == 1, "a fresh pool must not re-download the universe"


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_isolates_a_failing_league(session_factory) -> None:
    """One league erroring must not cost the others their sync."""
    await _seed_two_espn_leagues(session_factory)
    respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1111111").mock(
        return_value=httpx.Response(500)
    )
    respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/2222222").mock(
        return_value=httpx.Response(200, json=_pool_body(330.97))
    )

    async with session_factory() as session:
        error = await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert error is not None and "PPR League" in error

    async with session_factory() as session:
        rows = (await session.execute(select(PlayerPoolEntry))).scalars().all()

    assert {r.league_id for r in rows} == {"espn:2222222"}


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_refetches_when_the_marker_outlives_the_rows(
    session_factory,
) -> None:
    """A fresh cache marker over an EMPTY pool must not skip the league.

    The marker is written when the fetch succeeds; the rows land afterwards. Anything
    that interrupts that gap — a crash, a DB error, a caller that fetched without
    persisting — would otherwise leave the league unqueryable for a full 6h TTL with
    no retry. Observed for real: a smoke-test fetch wrote markers for three leagues
    that were then skipped on the next scheduled run.
    """
    await _seed_two_espn_leagues(session_factory)
    route = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1111111"
    ).mock(return_value=httpx.Response(200, json=_pool_body(364.86)))
    respx.get(f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/2222222").mock(
        return_value=httpx.Response(200, json=_pool_body(330.97))
    )

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())
    assert route.call_count == 1

    # Simulate the gap: marker stays fresh, rows vanish.
    async with session_factory() as session:
        await session.execute(
            delete(PlayerPoolEntry).where(PlayerPoolEntry.league_id == "espn:1111111")
        )
        await session.commit()

    async with session_factory() as session:
        await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert route.call_count == 2, "an empty pool must refetch despite a fresh marker"

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(PlayerPoolEntry).where(PlayerPoolEntry.league_id == "espn:1111111")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 2


@pytest.mark.asyncio
@respx.mock
async def test_refresh_player_pool_skips_disabled_leagues(session_factory) -> None:
    """Same `is_enabled` seam the discovery path honors.

    Observed live: a stale practice league 404s on every pull, which would otherwise
    pin the job to ok=False forever and leave Settings' "last refresh" line reading
    failed indefinitely. Disabling the league is the user-facing way to silence it.
    """
    await _seed_two_espn_leagues(session_factory)
    async with session_factory() as session:
        league = await session.get(League, "espn:2222222")
        league.is_enabled = False
        await session.commit()

    route_1 = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1111111"
    ).mock(return_value=httpx.Response(200, json=_pool_body(364.86)))
    route_2 = respx.get(
        f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/2222222"
    ).mock(return_value=httpx.Response(404))

    async with session_factory() as session:
        error = await fantasy_service.refresh_player_pool(session, settings=make_settings())

    assert error is None
    assert route_1.call_count == 1
    assert route_2.call_count == 0


# ---------------------------------------------------------------------------
# get_waivers (add-player-pool group 4)
# ---------------------------------------------------------------------------

WAIVER_LEAGUE = "espn:1111111"
WAIVER_TEAM = "espn:l-1111111-t-2"


async def _seed_waiver_league(session_factory) -> None:
    """One league, one user team with two starters, and a pool.

    The numbers are chosen so a weekly-vs-season unit mismatch is detectable: the
    starters' WEEKLY projections (`roster_slots.proj_points`) are ~1/17th of their
    season ones, exactly the real ratio (21.57 weekly vs 364.86 season for Gibbs).
    """
    async with session_factory() as session:
        session.add(
            League(
                id=WAIVER_LEAGUE,
                platform="espn",
                platform_id="1111111",
                name="Waiver League",
                season=2024,
                team_count=10,
                scoring_type="ppr",
                current_week=5,
            )
        )
        session.add(
            Team(
                id=WAIVER_TEAM,
                league_id=WAIVER_LEAGUE,
                platform="espn",
                platform_id="2",
                name="My Team",
                manager_name="Nick B",
                record_w=3,
                record_l=1,
                record_t=0,
                rank_current=2,
                rank_total=10,
                points_for=500.0,
                points_against=440.0,
                is_user_team=True,
            )
        )

        # (player_id, name, position, slot, weekly_proj, season_proj)
        starters = [
            ("espn:p-100", "Starter RB", "RB", "RB1", 14.0, 238.0),
            ("espn:p-101", "Weak RB", "RB", "RB2", 8.0, 136.0),
            ("espn:p-102", "Starter QB", "QB", "QB", 20.0, 340.0),
            ("espn:p-103", "Benched RB", "RB", "BN", 3.0, 51.0),
        ]
        for pid, name, pos, slot, weekly, season_proj in starters:
            session.add(
                Player(
                    id=pid,
                    platform="espn",
                    platform_id=pid.split("-")[-1],
                    name=name,
                    position=pos,
                    nfl_team="DET",
                    nfl_opponent=None,
                    nfl_game_id=None,
                    bye_week=5,
                    injury_status="ACTIVE",
                )
            )
            session.add(
                RosterSlot(
                    team_id=WAIVER_TEAM,
                    week=5,
                    slot=slot,
                    player_id=pid,
                    proj_points=weekly,
                    actual_points=0.0,
                    is_live=False,
                    game_state=None,
                    status_text="",
                )
            )
            session.add(
                PlayerPoolEntry(
                    league_id=WAIVER_LEAGUE,
                    player_id=pid,
                    status="ONTEAM",
                    on_team_id="2",
                    percent_owned=90.0,
                    percent_started=80.0,
                    season_proj_points=season_proj,
                    eligible_slots=json.dumps(
                        ["RB", "RB/WR", "FLEX", "BN", "IR"] if pos == "RB" else ["QB", "BN", "IR"]
                    ),
                )
            )

        # (player_id, name, position, season_proj, eligible)
        pool = [
            ("espn:p-200", "Better RB", "RB", 190.0, ["RB", "RB/WR", "FLEX", "BN", "IR"]),
            ("espn:p-201", "Worse RB", "RB", 90.0, ["RB", "RB/WR", "FLEX", "BN", "IR"]),
            ("espn:p-202", "Unprojected WR", "WR", None, ["WR", "RB/WR", "FLEX", "BN", "IR"]),
            ("espn:p-203", "Lonely K", "K", 120.0, ["K", "BN", "IR"]),
        ]
        for pid, name, pos, season_proj, eligible in pool:
            session.add(
                Player(
                    id=pid,
                    platform="espn",
                    platform_id=pid.split("-")[-1],
                    name=name,
                    position=pos,
                    nfl_team="GB",
                    nfl_opponent=None,
                    nfl_game_id=None,
                    bye_week=6,
                    injury_status="ACTIVE",
                )
            )
            session.add(
                PlayerPoolEntry(
                    league_id=WAIVER_LEAGUE,
                    player_id=pid,
                    status="FREEAGENT",
                    on_team_id=None,
                    percent_owned=20.0,
                    percent_started=1.0,
                    season_proj_points=season_proj,
                    eligible_slots=json.dumps(eligible),
                )
            )
        await session.commit()


def _by_name(data) -> dict:
    return {c.player.name: c for c in data.candidates}


@pytest.mark.asyncio
async def test_get_waivers_delta_uses_season_not_weekly_projections(session_factory) -> None:
    """Task 4.2a — the unit-mismatch regression.

    "Worse RB" projects 90.0 for the season; the user's weakest eligible starter
    ("Weak RB") projects 136.0. The honest delta is NEGATIVE: -46.0.

    Computed against `roster_slots.proj_points` instead, the weakest starter reads
    8.0, and the delta would come out at +82.0 — a strong recommendation to claim a
    player who is materially worse. That wrong answer looks entirely plausible in the
    UI, which is why this is pinned rather than left to review.
    """
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    worse = _by_name(data)["Worse RB"]
    assert worse.delta_vs_worst_starter == pytest.approx(-46.0)
    assert worse.delta_vs_worst_starter < 0, "a worse player must not read as an upgrade"

    better = _by_name(data)["Better RB"]
    assert better.delta_vs_worst_starter == pytest.approx(54.0)


@pytest.mark.asyncio
async def test_get_waivers_ignores_bench_and_ir_eligibility(session_factory) -> None:
    """The platform lists BN and IR as eligible for essentially every player. Counting
    them would let the comparison match a benched player — here "Benched RB" at 51.0,
    which is lower than every real starter and would inflate every RB's delta."""
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    worse = _by_name(data)["Worse RB"]
    # Against the weakest STARTER (136.0) -> -46.0.
    # Against the benched player (51.0)  -> +39.0.
    assert worse.delta_vs_worst_starter == pytest.approx(-46.0)


@pytest.mark.asyncio
async def test_get_waivers_matches_eligibility_across_slot_numbering(session_factory) -> None:
    """Starter slots are numbered (`RB1`, `RB2`); pool eligibility is not (`RB`). The
    comparison has to bridge the two, or no RB ever matches an RB starter."""
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    assert _by_name(data)["Better RB"].delta_vs_worst_starter is not None


@pytest.mark.asyncio
async def test_get_waivers_nulls_are_null_not_zero(session_factory) -> None:
    """Two distinct absences, neither of which may render as 0.0: a candidate with no
    projection, and a candidate with no eligible starter to compare against."""
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    unprojected = _by_name(data)["Unprojected WR"]
    assert unprojected.season_proj_points is None
    assert unprojected.delta_vs_worst_starter is None

    # The user starts no kicker, so there is nothing for a K to displace.
    kicker = _by_name(data)["Lonely K"]
    assert kicker.season_proj_points == pytest.approx(120.0)
    assert kicker.delta_vs_worst_starter is None


@pytest.mark.asyncio
async def test_get_waivers_excludes_rostered_players(session_factory) -> None:
    """ONTEAM rows exist for the comparison and must never be offered as claimable."""
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    assert all(c.status in ("FREEAGENT", "WAIVERS") for c in data.candidates)
    assert "Starter RB" not in _by_name(data)


@pytest.mark.asyncio
async def test_get_waivers_ranks_by_upgrade_not_raw_projection(session_factory) -> None:
    """The delta drives the ORDER, not just a column in it.

    Ranking by raw season projection produces a leaderboard of big scorers rather than
    of upgrades. Against real data that returned eight quarterbacks, every one with a
    negative delta — i.e. eight players worse than the one already being started.

    Here "Lonely K" (120.0) out-projects "Worse RB" (90.0) but has no eligible starter
    to displace, so it is unrankable and sorts BELOW the RB that is at least
    comparable. Projection only breaks ties among equally-ranked rows.
    """
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    names = [c.player.name for c in data.candidates]
    assert names == ["Better RB", "Worse RB", "Lonely K", "Unprojected WR"]

    deltas = [c.delta_vs_worst_starter for c in data.candidates]
    assert deltas[0] == pytest.approx(54.0)
    assert deltas[1] == pytest.approx(-46.0)
    assert deltas[2] is None and deltas[3] is None


@pytest.mark.asyncio
async def test_get_waivers_position_filter_and_limit(session_factory) -> None:
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        rbs = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5, position="RB")
        capped = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5, limit=2)

    assert {c.player.name for c in rbs.candidates} == {"Better RB", "Worse RB"}
    assert len(capped.candidates) == 2


@pytest.mark.asyncio
async def test_get_waivers_unknown_team_returns_none(session_factory) -> None:
    await _seed_waiver_league(session_factory)

    async with session_factory() as session:
        assert await fantasy_service.get_waivers(session, "espn:nope", week=5) is None


@pytest.mark.asyncio
async def test_get_waivers_empty_pool_is_not_an_error(session_factory) -> None:
    """A league whose pool has never synced returns an empty list, not a failure."""
    await _seed_waiver_league(session_factory)
    async with session_factory() as session:
        await session.execute(delete(PlayerPoolEntry))
        await session.commit()

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    assert data is not None
    assert data.candidates == []


@pytest.mark.asyncio
async def test_get_waivers_query_count_is_bounded(session_factory) -> None:
    """Task 4.3 — the delta must be computed in memory from one roster load, not with
    a query per candidate."""
    await _seed_waiver_league(session_factory)

    from sqlalchemy import event

    async with session_factory() as session:
        statements: list[str] = []

        def _count(conn, cursor, statement, *args):
            statements.append(statement)

        sync_engine = session.bind.sync_engine
        event.listen(sync_engine, "before_cursor_execute", _count)
        try:
            await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)
        finally:
            event.remove(sync_engine, "before_cursor_execute", _count)

    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    # The ceiling is 6: team, starters (slot + player_id + season proj in ONE outer
    # join), league, starter weekly projections, candidates, candidate projections
    # (weekly AND season in one `week IN (...)` select). Every one is constant.
    #
    # What this test actually protects is that the count does not scale with the number
    # of candidates — adding the weekly axis was worth two more queries only because
    # both are bulk `IN (...)` selects, and the starter roster was folded into a single
    # read rather than fetched twice.
    assert len(selects) <= 6, f"expected a bounded query count, got {len(selects)}: {selects}"


# ---------------------------------------------------------------------------
# get_league_standings (add-league-standings group 3)
# ---------------------------------------------------------------------------

STANDINGS_LEAGUE = "espn:3333333"


async def _seed_standings_league(session_factory, teams: list[tuple]) -> None:
    """`teams` is a list of (suffix, name, seed, wins, points_for)."""
    async with session_factory() as session:
        session.add(
            League(
                id=STANDINGS_LEAGUE,
                platform="espn",
                platform_id="3333333",
                name="Standings League",
                season=2024,
                team_count=len(teams),
                scoring_type="ppr",
                current_week=5,
            )
        )
        for suffix, name, seed, wins, pf in teams:
            session.add(
                Team(
                    id=f"espn:l-3333333-t-{suffix}",
                    league_id=STANDINGS_LEAGUE,
                    platform="espn",
                    platform_id=f"l-3333333-t-{suffix}",
                    name=name,
                    manager_name="Mgr",
                    record_w=wins,
                    record_l=5 - wins,
                    record_t=0,
                    rank_current=seed,
                    rank_total=len(teams),
                    points_for=pf,
                    points_against=100.0,
                    is_user_team=suffix == "1",
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_standings_follow_the_platform_seed_when_it_is_populated(session_factory) -> None:
    """The user asked to match ESPN's own ordering, so a real seed wins even when it
    disagrees with record — which it can, since ESPN applies tiebreaks this app does
    not model."""
    await _seed_standings_league(
        session_factory,
        [
            ("1", "Seeded Third", 3, 5, 900.0),  # best record, worst seed
            ("2", "Seeded First", 1, 1, 100.0),  # worst record, best seed
            ("3", "Seeded Second", 2, 3, 500.0),
        ],
    )

    async with session_factory() as session:
        data = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    assert [r.team.name for r in data.rows] == ["Seeded First", "Seeded Second", "Seeded Third"]
    assert [r.position for r in data.rows] == [1, 2, 3]


@pytest.mark.asyncio
async def test_standings_fall_back_to_record_when_every_seed_is_zero(session_factory) -> None:
    """ESPN reports seed 0 for every team in some leagues — GAS Lab is one live
    example. Seed alone would leave ten identical keys."""
    await _seed_standings_league(
        session_factory,
        [
            ("1", "Worst", 0, 1, 100.0),
            ("2", "Best", 0, 4, 800.0),
            ("3", "Middle", 0, 2, 400.0),
        ],
    )

    async with session_factory() as session:
        data = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    assert [r.team.name for r in data.rows] == ["Best", "Middle", "Worst"]


@pytest.mark.asyncio
async def test_a_zero_seed_sorts_after_a_real_one(session_factory) -> None:
    """A missing seed must not read as rank 0 and jump to the top."""
    await _seed_standings_league(
        session_factory,
        [
            ("1", "Unseeded", 0, 5, 900.0),
            ("2", "Seeded", 4, 0, 10.0),
        ],
    )

    async with session_factory() as session:
        data = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    assert [r.team.name for r in data.rows] == ["Seeded", "Unseeded"]


@pytest.mark.asyncio
async def test_a_total_tie_is_stable_across_calls(session_factory) -> None:
    """The regression D7's id floor exists for.

    Before week 1 every real team is 0-0-0 with 0.0 points and, in some leagues, seed
    0 — so every sort key is identical and the rendered order is whatever the query
    returned. Without the id tiebreak that can differ between two loads of the same
    page, and no test would notice by accident.
    """
    await _seed_standings_league(
        session_factory,
        [("3", "Gamma", 0, 0, 0.0), ("1", "Alpha", 0, 0, 0.0), ("2", "Beta", 0, 0, 0.0)],
    )

    async with session_factory() as session:
        first = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")
        second = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    order = [r.team.name for r in first.rows]
    assert order == [r.team.name for r in second.rows]
    # And it is the id order, not an accident of insertion order.
    assert order == ["Alpha", "Beta", "Gamma"]


@pytest.mark.asyncio
async def test_standings_carry_logo_urls_and_flag_the_user(session_factory) -> None:
    await _seed_standings_league(session_factory, [("1", "Mine", 1, 3, 500.0)])
    async with session_factory() as session:
        team = await session.get(Team, "espn:l-3333333-t-1")
        team.logo_source_url = "https://g.espncdn.com/lm-static/ffl/images/default_logos/6.svg"
        await session.commit()

    async with session_factory() as session:
        data = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    row = data.rows[0]
    assert row.team.is_user_team is True
    # A LOCAL url — never ESPN's, which 401s an unauthenticated browser.
    assert row.team.logo_url == "/api/team-logos/espn/l-3333333-t-1"


@pytest.mark.asyncio
async def test_a_team_without_a_logo_has_a_null_logo_url(session_factory) -> None:
    """Null rather than a crest URL, so the client can skip the request entirely
    instead of fetching a placeholder it could render locally."""
    await _seed_standings_league(session_factory, [("1", "Mine", 1, 3, 500.0)])

    async with session_factory() as session:
        data = await fantasy_service.get_league_standings(session, "espn:l-3333333-t-1")

    assert data.rows[0].team.logo_url is None


@pytest.mark.asyncio
async def test_standings_unknown_team_returns_none(session_factory) -> None:
    async with session_factory() as session:
        assert await fantasy_service.get_league_standings(session, "espn:nope") is None


# --------------------------------------------------------------------------------------
# Third-party projections on the read path (add-sleeper-projections)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scoring_type,expected",
    [
        ("ppr", 20.0),
        ("half_ppr", 18.0),
        ("standard", 16.0),
        # A `custom` league gets None, never the PPR number: a confident wrong answer is
        # worse than an empty column, and `stats_json` keeps what a real computation needs.
        ("custom", None),
        (None, None),
    ],
)
def test_resolve_points_picks_the_league_s_own_scoring_format(scoring_type, expected) -> None:
    row = PlayerProjection(
        player_id="espn:p-1",
        season=2026,
        week=1,
        source="rotowire",
        pts_ppr=20.0,
        pts_half_ppr=18.0,
        pts_std=16.0,
        fetched_at=datetime(2026, 9, 3),
    )
    assert fantasy_service._resolve_points(row, scoring_type) == expected


def test_resolve_points_of_a_missing_row_is_none() -> None:
    assert fantasy_service._resolve_points(None, "ppr") is None


async def test_waivers_carry_both_a_weekly_and_a_season_upgrade(session_factory) -> None:
    """The two horizons disagree often enough to matter — a bye-week starter is a
    season-long keep and a week-one hole — so a claim needs both numbers, not one."""
    await _seed_waiver_league(session_factory)
    async with session_factory() as session:
        league = await session.get(League, WAIVER_LEAGUE)
        # Weekly projections: the weakest eligible RB starter ("Weak RB") is poor THIS
        # week, and the free-agent "Better RB" is strong.
        for player_id, pts in [("espn:p-101", 4.0), ("espn:p-100", 12.0), ("espn:p-200", 15.0)]:
            session.add(
                PlayerProjection(
                    player_id=player_id,
                    season=league.season,
                    week=5,
                    source="rotowire",
                    pts_ppr=pts,
                    pts_half_ppr=pts,
                    pts_std=pts,
                    match_tier="espn_id",
                    fetched_at=datetime(2026, 9, 3),
                )
            )
        await session.commit()

    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)

    target = next(c for c in data.candidates if c.player.id == "espn:p-200")
    assert target.week_proj_points == pytest.approx(15.0)
    assert target.delta_vs_worst_starter_week == pytest.approx(11.0)
    # The season axis is untouched by the weekly one.
    assert target.delta_vs_worst_starter is not None


async def test_a_candidate_with_no_weekly_projection_reports_null_not_zero(
    session_factory,
) -> None:
    """Same rule the season delta already follows: "no comparison" is not "no upgrade"."""
    await _seed_waiver_league(session_factory)
    async with session_factory() as session:
        data = await fantasy_service.get_waivers(session, WAIVER_TEAM, week=5)
    for candidate in data.candidates:
        assert candidate.week_proj_points is None
        assert candidate.delta_vs_worst_starter_week is None
