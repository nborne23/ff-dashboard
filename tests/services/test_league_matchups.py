"""`services/league_matchups.py` — every pairing in a league: the discovery writes (ESPN
from the payload it already fetches, Yahoo from one `/scoreboard` per league), and the
read paths behind the All Matchups screen and its read-only head-to-head."""

import copy
import json
import re
from datetime import datetime
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    League,
    LiveNflGame,
    Matchup,
    MatchupSlot,
    Player,
    RosterSlot,
    Team,
)
from backend.gridiron.platforms.yahoo.client import BASE_URL as YAHOO_BASE
from backend.gridiron.services import differ, events, fantasy_service, league_matchups, live_state
from tests.services.test_fantasy_service import (
    ESPN_BASE,
    ESPN_SWID,
    _connect_espn,
    _connect_yahoo,
    _single_league_yahoo_leagues,
    load_fixture,
    make_settings,
)

LEAGUE = "yahoo:461.l.123456"


T1, T2, T3, T4 = (f"yahoo:461.l.123456.t.{n}" for n in (1, 2, 3, 4))


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "league-matchups.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


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


# --- Seeding ---------------------------------------------------------------------------


def _team(n: int, name: str, *, wins: int, seed: int, user: bool = False) -> Team:
    return Team(
        id=f"yahoo:461.l.123456.t.{n}",
        league_id=LEAGUE,
        platform="yahoo",
        platform_id=f"461.l.123456.t.{n}",
        name=name,
        manager_name=f"Manager {n}",
        record_w=wins,
        record_l=7 - wins,
        record_t=0,
        rank_current=seed,
        rank_total=4,
        points_for=100.0 * wins,
        points_against=500.0,
        is_user_team=user,
    )


def _player(n: int, position: str, nfl_team: str) -> Player:
    return Player(
        id=f"yahoo:461.p.{n}",
        platform="yahoo",
        platform_id=f"461.p.{n}",
        name=f"Player {n}",
        position=position,
        nfl_team=nfl_team,
    )


def _slot(team: str, slot: str, player: int, pts: float, week: int = 8) -> RosterSlot:
    return RosterSlot(
        team_id=team,
        week=week,
        slot=slot,
        player_id=f"yahoo:461.p.{player}",
        proj_points=10.0,
        actual_points=pts,
    )


def _matchup(mid: str, home: str, away: str, hs: float, as_: float, week: int = 8) -> Matchup:
    return Matchup(
        id=mid,
        league_id=LEAGUE,
        week=week,
        home_team_id=home,
        away_team_id=away,
        home_score=hs,
        away_score=as_,
        home_proj=hs + 10,
        away_proj=as_ + 10,
        is_complete=False,
    )


async def _seed_league(session_factory) -> None:
    """A 4-team Yahoo league in week 8: the user (T2, 3rd by seed) plays T1, and T3 plays
    T4. Only the user's matchup has persisted slots — T3/T4's must be paired from
    rosters, the way a Yahoo pairing other than the user's always is."""
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE,
                platform="yahoo",
                platform_id="461.l.123456",
                name="Battle Royale",
                season=2026,
                team_count=4,
                scoring_type="ppr",
                current_week=8,
            )
        )
        session.add_all(
            [
                _team(1, "Trash Pandas", wins=6, seed=1),
                _team(2, "Scranton Stranglers", wins=3, seed=3, user=True),
                _team(3, "HellFire Club", wins=3, seed=4),
                _team(4, "Toms Tip-Top Team", wins=6, seed=2),
            ]
        )
        session.add_all(
            [
                _player(1, "QB", "KC"),
                _player(2, "QB", "BUF"),
                _player(3, "QB", "DET"),
                _player(4, "QB", "PHI"),
                _player(5, "RB", "KC"),
                _player(6, "RB", "DAL"),
            ]
        )
        session.add_all(
            [
                _slot(T1, "QB", 1, 20.0),
                _slot(T2, "QB", 2, 18.0),
                _slot(T3, "QB", 3, 22.5),
                _slot(T3, "RB1", 5, 7.0),
                _slot(T3, "BN", 6, 30.0),
                _slot(T4, "QB", 4, 11.0),
                _slot(T4, "RB1", 6, 4.0),
            ]
        )
        session.add_all(
            [
                _matchup("yahoo:461.l.123456.mu.8", T1, T2, 20.0, 18.0),
                _matchup("yahoo:461.l.123456.mu.8.3v4", T3, T4, 29.5, 15.0),
                _matchup("yahoo:461.l.123456.mu.7", T2, T3, 99.0, 88.0, week=7),
            ]
        )
        session.add(
            MatchupSlot(
                matchup_id="yahoo:461.l.123456.mu.8",
                slot="QB",
                home_player_id="yahoo:461.p.1",
                away_player_id="yahoo:461.p.2",
                home_pts=20.0,
                away_pts=18.0,
            )
        )
        await session.commit()


# --- Reads -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lists_every_pairing_with_the_users_matchup_first(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        data = await league_matchups.get_league_matchups(session, T2, 8)

    assert data is not None
    assert data.league.name == "Battle Royale"
    assert data.week == 8
    assert [e.matchup.id for e in data.matchups] == [
        "yahoo:461.l.123456.mu.8",
        "yahoo:461.l.123456.mu.8.3v4",
    ]
    mine = data.matchups[0]
    assert mine.is_user_matchup is True
    assert mine.home.team.name == "Trash Pandas"
    assert mine.away.team.manager_name == "Manager 2"
    assert data.matchups[1].is_user_matchup is False


@pytest.mark.asyncio
async def test_positions_follow_the_standings_not_the_raw_seed(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        data = await league_matchups.get_league_matchups(session, T2, 8)

    other = data.matchups[1]
    assert (other.home.team.id, other.home.position) == (T3, 4)
    assert (other.away.team.id, other.away.position) == (T4, 2)
    assert other.away.team.record.w == 6


@pytest.mark.asyncio
async def test_other_matchups_order_by_their_best_placed_team(session_factory) -> None:
    await _seed_league(session_factory)
    async with session_factory() as session:
        session.add_all(
            [
                _team(5, "Smeg Heads", wins=0, seed=6),
                _team(6, "Cleveland McClowns", wins=1, seed=5),
                _matchup("yahoo:461.l.123456.mu.8.5v6", f"{LEAGUE}.t.5", f"{LEAGUE}.t.6", 1, 2),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        data = await league_matchups.get_league_matchups(session, T2, 8)

    assert [e.matchup.id for e in data.matchups][1:] == [
        "yahoo:461.l.123456.mu.8.3v4",  # holds the 2nd-placed team
        "yahoo:461.l.123456.mu.8.5v6",  # best team is 5th
    ]


@pytest.mark.asyncio
async def test_remaining_and_live_count_starters_only(session_factory) -> None:
    await _seed_league(session_factory)
    live_state.set_current_live_state("live")
    async with session_factory() as session:
        session.add_all(
            [
                LiveNflGame(
                    nfl_game_id="g1",
                    home_team="DET",
                    away_team="CHI",
                    home_score=7,
                    away_score=3,
                    state="in",
                    kickoff_at=datetime(2026, 10, 25, 17, 0),
                ),
                LiveNflGame(
                    nfl_game_id="g2",
                    home_team="DAL",
                    away_team="NYG",
                    home_score=0,
                    away_score=0,
                    state="in",
                    kickoff_at=datetime(2026, 10, 25, 17, 0),
                ),
                LiveNflGame(
                    nfl_game_id="g3",
                    home_team="KC",
                    away_team="LV",
                    home_score=21,
                    away_score=0,
                    state="post",
                    kickoff_at=datetime(2026, 10, 23, 0, 15),
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        data = await league_matchups.get_league_matchups(session, T2, 8)

    other = data.matchups[1]
    # T3: QB (DET, in) remaining + live; RB1 (KC, post) done; the BN player doesn't count.
    assert (other.home.remaining, other.home.is_live) == (1, True)
    # T4: QB (PHI, no game row -> "pre") and RB1 (DAL, in).
    assert (other.away.remaining, other.away.is_live) == (2, True)


@pytest.mark.asyncio
async def test_a_week_with_nothing_stored_is_an_empty_list(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        data = await league_matchups.get_league_matchups(session, T2, 3)

    assert data is not None
    assert data.matchups == []


@pytest.mark.asyncio
async def test_unknown_team_is_none(session_factory) -> None:
    async with session_factory() as session:
        assert await league_matchups.get_league_matchups(session, "yahoo:nope", 8) is None
        assert await league_matchups.get_league_matchup_detail(session, "yahoo:nope", "x") is None


@pytest.mark.asyncio
async def test_detail_uses_persisted_slots_when_there_are_any(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        detail = await league_matchups.get_league_matchup_detail(
            session, T2, "yahoo:461.l.123456.mu.8"
        )

    assert detail is not None
    assert detail.is_user_matchup is True
    assert [(s.slot, s.home_pts, s.away_pts) for s in detail.slots] == [("QB", 20.0, 18.0)]


@pytest.mark.asyncio
async def test_detail_pairs_other_teams_from_their_rosters(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        detail = await league_matchups.get_league_matchup_detail(
            session, T2, "yahoo:461.l.123456.mu.8.3v4"
        )

    assert detail is not None
    assert detail.is_user_matchup is False
    assert detail.week == 8
    assert (detail.home.team.name, detail.away.team.name) == ("HellFire Club", "Toms Tip-Top Team")
    # Starters paired by slot in display order; the bench player is left out.
    assert [(s.slot, s.home_player.name, s.away_player.name) for s in detail.slots] == [
        ("QB", "Player 3", "Player 4"),
        ("RB1", "Player 5", "Player 6"),
    ]
    assert [(s.home_pts, s.away_pts) for s in detail.slots] == [(22.5, 11.0), (7.0, 4.0)]


@pytest.mark.asyncio
async def test_detail_takes_its_week_from_the_matchup(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        detail = await league_matchups.get_league_matchup_detail(
            session, T2, "yahoo:461.l.123456.mu.7"
        )

    assert detail is not None
    assert detail.week == 7
    # Nobody's week-7 roster is stored: a totals-only matchup, not an error.
    assert detail.slots == []
    assert detail.matchup.home_score == 99.0


@pytest.mark.asyncio
async def test_detail_refuses_a_matchup_from_another_league(session_factory) -> None:
    await _seed_league(session_factory)
    async with session_factory() as session:
        session.add(
            League(
                id="yahoo:461.l.999",
                platform="yahoo",
                platform_id="461.l.999",
                name="Other",
                season=2026,
                team_count=2,
                scoring_type="ppr",
                current_week=8,
            )
        )
        session.add(
            Matchup(
                id="yahoo:461.l.999.mu.8.1v2",
                league_id="yahoo:461.l.999",
                week=8,
                home_team_id="yahoo:461.l.999.t.1",
                away_team_id="yahoo:461.l.999.t.2",
            )
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await league_matchups.get_league_matchup_detail(session, T2, "yahoo:461.l.999.mu.8.1v2")
            is None
        )


# --- Differ ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fingerprint_moves_when_only_another_matchup_scores(session_factory) -> None:
    await _seed_league(session_factory)

    async with session_factory() as session:
        before = await differ.league_matchups_fingerprints(session, 8)
        row = await session.get(Matchup, "yahoo:461.l.123456.mu.8.3v4")
        row.home_score = 35.5
        await session.commit()
    async with session_factory() as session:
        after = await differ.league_matchups_fingerprints(session, 8)

    assert set(before) == {f"matchups:{LEAGUE}"}
    assert before[f"matchups:{LEAGUE}"] != after[f"matchups:{LEAGUE}"]


@pytest.mark.asyncio
async def test_fingerprint_skips_disabled_leagues(session_factory) -> None:
    await _seed_league(session_factory)
    async with session_factory() as session:
        (await session.get(League, LEAGUE)).is_enabled = False
        await session.commit()

    async with session_factory() as session:
        assert await differ.league_matchups_fingerprints(session, 8) == {}


# --- Yahoo discovery -------------------------------------------------------------------


def _four_team_standings() -> dict:
    raw = load_fixture("yahoo", "standings.json")
    teams = raw["fantasy_content"]["league"][1]["standings"][0]["teams"]
    for n in (3, 4):
        clone = json.loads(json.dumps(teams["1"]).replace(".t.2", f".t.{n}"))
        clone["team"][0][1] = {"team_id": str(n)}
        clone["team"][0][2] = {"name": f"Team {n}"}
        teams[str(n - 1)] = clone
    teams["count"] = 4
    return raw


def _scoreboard(*pairs: tuple[int, int, float, float]) -> dict:
    raw = load_fixture("yahoo", "scoreboard.json")
    scoreboard = raw["fantasy_content"]["league"][1]["scoreboard"]
    template = scoreboard["0"]["matchups"]["0"]
    matchups: dict = {"count": len(pairs)}
    for i, (home, away, hs, as_) in enumerate(pairs):
        item = copy.deepcopy(template)
        sides = item["matchup"]["teams"]
        for key, n, pts in (("0", home, hs), ("1", away, as_)):
            sides[key]["team"][0][0] = {"team_key": f"461.l.123456.t.{n}"}
            sides[key]["team"][1]["team_points"]["total"] = str(pts)
        matchups[str(i)] = item
    scoreboard["0"]["matchups"] = matchups
    return raw


def _mock_four_team_yahoo(scoreboards: dict[int, dict]) -> dict[int, respx.Route]:
    """Discovery for a 4-team league in week 14; `scoreboards` maps week -> payload."""
    roster = load_fixture("yahoo", "roster.json")
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_codes=nfl").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "games.json"))
    )
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_keys=461/leagues").mock(
        return_value=httpx.Response(200, json=_four_team_leagues())
    )
    respx.get(f"{YAHOO_BASE}/league/461.l.123456/standings").mock(
        return_value=httpx.Response(200, json=_four_team_standings())
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.1/matchups;weeks=14").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "matchup.json"))
    )
    for n in (1, 2, 3, 4):
        respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.{n}/roster;week=14/players/stats").mock(
            return_value=httpx.Response(
                200, json=json.loads(json.dumps(roster).replace(".t.1", f".t.{n}"))
            )
        )
    return {
        week: respx.get(f"{YAHOO_BASE}/league/461.l.123456/scoreboard;week={week}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        for week, payload in scoreboards.items()
    }


def _four_team_leagues() -> dict:
    raw = _single_league_yahoo_leagues()
    league = raw["fantasy_content"]["users"]["0"]["user"][1]["games"]["0"]["game"][1]["leagues"]
    league["0"]["league"][0]["num_teams"] = 4
    return raw


@pytest.mark.asyncio
@respx.mock
async def test_yahoo_discovery_stores_the_rest_of_the_leagues_pairings(session_factory) -> None:
    await _connect_yahoo(session_factory)
    live_state.set_current_live_state("live")  # no backfill: current week only
    routes = _mock_four_team_yahoo({14: _scoreboard((1, 2, 88.24, 76.1), (3, 4, 101.5, 99.0))})

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())
    assert outcomes["yahoo"].ok is True
    assert routes[14].call_count == 1

    async with session_factory() as session:
        rows = (await session.execute(select(Matchup).where(Matchup.week == 14))).scalars().all()
    by_id = {m.id: m for m in rows}
    # The user's pairing keeps its legacy id and slots; the scoreboard doesn't duplicate it.
    assert set(by_id) == {"yahoo:461.l.123456.mu.14", "yahoo:461.l.123456.mu.14.3v4"}
    other = by_id["yahoo:461.l.123456.mu.14.3v4"]
    assert (other.home_team_id, other.away_team_id) == (T3, T4)
    assert (other.home_score, other.away_score) == (101.5, 99.0)

    async with session_factory() as session:
        detail = await league_matchups.get_league_matchup_detail(session, T1, other.id)
    assert detail is not None
    assert detail.slots  # paired from the rosters `_sync_other_yahoo_rosters` stored


@pytest.mark.asyncio
@respx.mock
async def test_yahoo_backfills_a_few_past_weeks_per_run_off_live(session_factory) -> None:
    await _connect_yahoo(session_factory)
    pairs = ((1, 2, 70.0, 60.0), (3, 4, 50.0, 40.0))
    routes = _mock_four_team_yahoo({w: _scoreboard(*pairs) for w in range(10, 15)})

    async with session_factory() as session:
        await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert [w for w, r in routes.items() if r.called] == [12, 13, 14]
    async with session_factory() as session:
        week_13 = (await session.execute(select(Matchup).where(Matchup.week == 13))).scalars().all()
    assert {m.id for m in week_13} == {
        "yahoo:461.l.123456.mu.13.1v2",
        "yahoo:461.l.123456.mu.13.3v4",
    }

    async with session_factory() as session:
        await fantasy_service.refresh_discovery(session, settings=make_settings())
    # The next run moves on to older weeks rather than re-fetching complete ones.
    assert routes[11].called and routes[10].called


@pytest.mark.asyncio
@respx.mock
async def test_yahoo_backfill_never_overwrites_a_stored_matchup(session_factory) -> None:
    await _connect_yahoo(session_factory)
    _mock_four_team_yahoo(
        {w: _scoreboard((1, 2, 1.0, 2.0), (3, 4, 3.0, 4.0)) for w in range(12, 15)}
    )
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE,
                platform="yahoo",
                platform_id="461.l.123456",
                name="x",
                season=2025,
                team_count=4,
                scoring_type="ppr",
                current_week=14,
            )
        )
        session.add(_matchup("yahoo:461.l.123456.mu.13", T1, T2, 120.0, 110.0, week=13))
        await session.commit()

    async with session_factory() as session:
        await fantasy_service.refresh_discovery(session, settings=make_settings())

    async with session_factory() as session:
        week_13 = (await session.execute(select(Matchup).where(Matchup.week == 13))).scalars().all()
    by_id = {m.id: m for m in week_13}
    assert set(by_id) == {"yahoo:461.l.123456.mu.13", "yahoo:461.l.123456.mu.13.3v4"}
    assert by_id["yahoo:461.l.123456.mu.13"].home_score == 120.0
    assert by_id["yahoo:461.l.123456.mu.13"].home_proj == 130.0


@pytest.mark.asyncio
@respx.mock
async def test_a_malformed_scoreboard_never_fails_yahoo_discovery(session_factory) -> None:
    await _connect_yahoo(session_factory)
    live_state.set_current_live_state("live")
    _mock_four_team_yahoo({14: {"fantasy_content": {"league": [{}, {"nope": {}}]}}})

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is True
    async with session_factory() as session:
        assert await session.get(Matchup, "yahoo:461.l.123456.mu.14") is not None


@pytest.mark.asyncio
@respx.mock
async def test_a_rate_limited_scoreboard_still_puts_yahoo_in_cooldown(session_factory) -> None:
    await _connect_yahoo(session_factory)
    live_state.set_current_live_state("live")
    _mock_four_team_yahoo({})
    respx.get(f"{YAHOO_BASE}/league/461.l.123456/scoreboard;week=14").mock(
        return_value=httpx.Response(429)
    )

    with patch("backend.gridiron.platforms.yahoo.client.asyncio.sleep", new=AsyncMock()):
        async with session_factory() as session:
            outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())

    assert outcomes["yahoo"].ok is False
    assert "rate_limited" in (outcomes["yahoo"].error or "")


# --- ESPN discovery --------------------------------------------------------------------


def _espn_league_with_four_teams() -> dict:
    raw = load_fixture("espn", "league.json")
    rival = raw["teams"][1]
    for n in (3, 4):
        clone = copy.deepcopy(rival)
        clone["id"] = n
        for key in ("name", "location", "nickname", "abbrev"):
            if key in clone:
                clone[key] = f"{clone[key]} {n}"
        clone.pop("owners", None)
        raw["teams"].append(clone)
    return raw


def _espn_roster_matchup_with_whole_schedule() -> dict:
    """The fixture's one week-10 entry (2 v 5), plus 3 v 4 the same week, two week-9
    entries (totals only — outside the fetched scoring period), a week-11 entry, and a
    bye entry with no away side."""
    raw = load_fixture("espn", "roster_matchup.json")
    mine = raw["schedule"][0]
    other = copy.deepcopy(mine)
    other.update(id=5002)
    other["home"]["teamId"], other["away"]["teamId"] = 3, 4
    other["home"]["totalPoints"], other["away"]["totalPoints"] = 64.5, 71.25

    def totals(entry_id: int, period: int, home: int, away: int, hs: float, as_: float) -> dict:
        return {
            "id": entry_id,
            "matchupPeriodId": period,
            "winner": "HOME" if hs > as_ else "AWAY",
            "home": {"teamId": home, "totalPoints": hs},
            "away": {"teamId": away, "totalPoints": as_},
        }

    raw["schedule"] += [
        other,
        totals(4001, 9, 2, 3, 101.5, 90.0),
        totals(4002, 9, 5, 4, 80.0, 85.0),
        {"id": 6001, "matchupPeriodId": 11, "winner": "UNDECIDED", "home": {"teamId": 2}},
        totals(6002, 11, 3, 5, 0.0, 0.0),
    ]
    return raw


def _mock_espn(roster_raw: dict) -> None:
    league_path = f"{ESPN_BASE}/apis/v3/games/ffl/seasons/2024/segments/0/leagues/1234567"
    respx.get(league_path, params={"scoringPeriodId": "10"}).mock(
        return_value=httpx.Response(200, json=roster_raw)
    )
    respx.get(league_path).mock(
        return_value=httpx.Response(200, json=_espn_league_with_four_teams())
    )
    respx.get(
        url__regex=rf"https://fan\.api\.espn\.com/apis/v2/fans/{re.escape(quote(ESPN_SWID, safe=''))}.*"
    ).mock(return_value=httpx.Response(200, json={"preferences": []}))


@pytest.mark.asyncio
@respx.mock
async def test_espn_discovery_stores_every_pairing_from_the_same_payload(session_factory) -> None:
    await _connect_espn(session_factory)
    _mock_espn(_espn_roster_matchup_with_whole_schedule())

    async with session_factory() as session:
        outcomes = await fantasy_service.refresh_discovery(session, settings=make_settings())
    assert outcomes["espn"].ok is True

    async with session_factory() as session:
        rows = (await session.execute(select(Matchup))).scalars().all()
        by_id = {m.id: m for m in rows}
        other_slots = (
            (
                await session.execute(
                    select(MatchupSlot).where(
                        MatchupSlot.matchup_id == "espn:l-1234567-m-5002-w-10"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert set(by_id) == {
        "espn:l-1234567-m-5001-w-10",
        "espn:l-1234567-m-5002-w-10",
        "espn:l-1234567-m-4001-w-9",
        "espn:l-1234567-m-4002-w-9",
    }  # no week-11 rows, no bye row
    current = by_id["espn:l-1234567-m-5002-w-10"]
    assert (current.home_team_id, current.away_team_id) == (
        "espn:l-1234567-t-3",
        "espn:l-1234567-t-4",
    )
    assert (current.home_score, current.away_score) == (64.5, 71.25)
    assert other_slots  # the fetched week's pairings come with their starters
    past = by_id["espn:l-1234567-m-4001-w-9"]
    assert (past.home_score, past.away_score, past.is_complete) == (101.5, 90.0, True)


@pytest.mark.asyncio
@respx.mock
async def test_espn_past_weeks_are_insert_only_and_wait_out_live_games(session_factory) -> None:
    await _connect_espn(session_factory)
    _mock_espn(_espn_roster_matchup_with_whole_schedule())
    async with session_factory() as session:
        session.add(
            Matchup(
                id="espn:l-1234567-m-4001-w-9",
                league_id="espn:1234567",
                week=9,
                home_team_id="espn:l-1234567-t-2",
                away_team_id="espn:l-1234567-t-3",
                home_score=101.5,
                away_score=90.0,
                home_proj=118.0,
                away_proj=104.0,
                is_complete=True,
            )
        )
        await session.commit()

    live_state.set_current_live_state("live")
    async with session_factory() as session:
        await fantasy_service.refresh_discovery(session, settings=make_settings())
    async with session_factory() as session:
        assert await session.get(Matchup, "espn:l-1234567-m-4002-w-9") is None

    live_state.set_current_live_state("off_day")
    async with session_factory() as session:
        await fantasy_service.refresh_discovery(session, settings=make_settings())
    async with session_factory() as session:
        assert await session.get(Matchup, "espn:l-1234567-m-4002-w-9") is not None
        kept = await session.get(Matchup, "espn:l-1234567-m-4001-w-9")
        assert (kept.home_proj, kept.away_proj) == (118.0, 104.0)
