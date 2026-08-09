"""Unit tests for `espn.mapper` against the synthetic fixtures in `tests/fixtures/espn/`."""

import copy
import json
from pathlib import Path

import pytest

from backend.gridiron.platforms.espn import mapper
from backend.gridiron.platforms.espn.slot_table import UnknownSlotError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "espn"

USER_SWID = "{ABC12345-DEAD-BEEF-0000-111111111111}"
RIVAL_SWID = "{ZZZ99999-DEAD-BEEF-0000-222222222222}"


@pytest.fixture
def league_raw() -> dict:
    return json.loads((FIXTURES / "league.json").read_text())


@pytest.fixture
def roster_matchup_raw() -> dict:
    return json.loads((FIXTURES / "roster_matchup.json").read_text())


@pytest.fixture
def completed_week5_raw() -> dict:
    return json.loads((FIXTURES / "roster_matchup_completed_week5.json").read_text())


# --- map_league ---------------------------------------------------------------


def test_map_league(league_raw: dict) -> None:
    league = mapper.map_league(league_raw)

    assert league.id == "espn:1234567"
    assert league.platform == "espn"
    assert league.platform_id == "1234567"
    assert league.name == "Highland Bombers League"
    assert league.season == 2024
    assert league.team_count == 10
    assert league.scoring_type == "ppr"
    assert league.current_week == 10


# --- resolve_user_team_id / manager_name_for ------------------------------------


def test_resolve_user_team_id_matches_swid_to_owners(league_raw: dict) -> None:
    assert mapper.resolve_user_team_id(league_raw, USER_SWID) == 2
    assert mapper.resolve_user_team_id(league_raw, RIVAL_SWID) == 5


def test_resolve_user_team_id_returns_none_when_no_team_owned(league_raw: dict) -> None:
    assert mapper.resolve_user_team_id(league_raw, "{NOT-A-MEMBER}") is None


def test_manager_name_for_looks_up_display_name(league_raw: dict) -> None:
    assert mapper.manager_name_for(league_raw, 2) == "Nick B"
    assert mapper.manager_name_for(league_raw, 5) == "Rival Manager"


# --- map_team ------------------------------------------------------------------


def test_map_team(league_raw: dict) -> None:
    team_raw = next(t for t in league_raw["teams"] if t["id"] == 2)
    team = mapper.map_team(team_raw, league_id=1234567)

    assert team.id == "espn:l-1234567-t-2"
    assert team.league_id == "espn:1234567"
    assert team.name == "Highland Bombers"
    assert team.record.w == 6
    assert team.record.l == 3
    assert team.record.t == 0
    assert team.points_for == 987.4
    assert team.points_against == 875.1
    assert team.rank.current == 2


def test_map_team_falls_back_to_location_nickname_when_name_missing(league_raw: dict) -> None:
    team_raw = copy.deepcopy(next(t for t in league_raw["teams"] if t["id"] == 5))
    del team_raw["name"]
    team = mapper.map_team(team_raw, league_id=1234567)
    assert team.name == "Rival Squad"


# --- map_roster ------------------------------------------------------------------


def test_map_roster_returns_every_player_across_both_sides(roster_matchup_raw: dict) -> None:
    slots = mapper.map_roster(roster_matchup_raw, week=10)
    assert len(slots) == 13 + 11  # home roster + away roster


def test_map_roster_numbers_rb_and_wr_by_order(roster_matchup_raw: dict) -> None:
    slots = mapper.map_roster(roster_matchup_raw, week=10)
    home_slots = {s.player.name: s.slot for s in slots if s.team_id == "espn:l-1234567-t-2"}

    assert home_slots["Christian McCaffrey"] == "RB1"
    assert home_slots["Bijan Robinson"] == "RB2"
    assert home_slots["Justin Jefferson"] == "WR1"
    assert home_slots["Amon-Ra St. Brown"] == "WR2"
    assert home_slots["Josh Allen"] == "QB"
    assert home_slots["Travis Kelce"] == "TE"
    assert home_slots["Tony Pollard"] == "FLEX"
    assert home_slots["Baltimore Ravens"] == "DST"
    assert home_slots["Justin Tucker"] == "K"
    assert home_slots["J.K. Dobbins"] == "IR"
    bench_names = {"Jordan Love", "Rashee Rice", "De'Von Achane"}
    assert {name: slot for name, slot in home_slots.items() if name in bench_names} == {
        name: "BN" for name in bench_names
    }


def test_map_roster_reads_actual_and_projected_points(roster_matchup_raw: dict) -> None:
    slots = mapper.map_roster(roster_matchup_raw, week=10)
    josh_allen = next(s for s in slots if s.player.name == "Josh Allen")
    assert josh_allen.actual_points == 24.56
    assert josh_allen.proj_points == 21.3


def test_map_roster_translates_position_and_injury_and_nfl_team(roster_matchup_raw: dict) -> None:
    slots = mapper.map_roster(roster_matchup_raw, week=10)
    st_brown = next(s for s in slots if s.player.name == "Amon-Ra St. Brown")
    assert st_brown.player.position == "WR"
    assert st_brown.player.nfl_team == "DET"
    assert st_brown.player.injury_status == "Q"

    dobbins = next(s for s in slots if s.player.name == "J.K. Dobbins")
    assert dobbins.player.injury_status == "IR"
    assert dobbins.actual_points == 0.0


def test_map_roster_unknown_slot_id_raises(roster_matchup_raw: dict) -> None:
    tampered = copy.deepcopy(roster_matchup_raw)
    tampered["schedule"][0]["home"]["rosterForCurrentScoringPeriod"]["entries"][0][
        "lineupSlotId"
    ] = 9999
    with pytest.raises(UnknownSlotError):
        mapper.map_roster(tampered, week=10)


# --- map_matchup ------------------------------------------------------------------


def test_map_matchup_for_user_team(roster_matchup_raw: dict) -> None:
    matchup, slots = mapper.map_matchup(roster_matchup_raw, week=10, user_team_id=2)

    assert matchup.id == "espn:l-1234567-m-5001-w-10"
    assert matchup.league_id == "espn:1234567"
    assert matchup.week == 10
    assert matchup.home_team_id == "espn:l-1234567-t-2"
    assert matchup.away_team_id == "espn:l-1234567-t-5"
    assert matchup.home_score == 115.36
    assert matchup.away_score == 102.2
    assert matchup.home_proj == pytest.approx(117.8)
    assert matchup.away_proj == pytest.approx(112.5)
    assert matchup.is_complete is False

    assert {s.slot for s in slots} == {
        "QB",
        "RB1",
        "RB2",
        "WR1",
        "WR2",
        "TE",
        "FLEX",
        "DST",
        "K",
    }
    qb_slot = next(s for s in slots if s.slot == "QB")
    assert qb_slot.home_player.name == "Josh Allen"
    assert qb_slot.away_player.name == "Patrick Mahomes"
    assert qb_slot.home_pts == 24.56
    assert qb_slot.away_pts == 19.3


def test_map_matchup_works_from_either_side(roster_matchup_raw: dict) -> None:
    matchup, _ = mapper.map_matchup(roster_matchup_raw, week=10, user_team_id=5)
    assert matchup.home_team_id == "espn:l-1234567-t-2"
    assert matchup.away_team_id == "espn:l-1234567-t-5"


def test_map_matchup_raises_when_team_not_in_schedule(roster_matchup_raw: dict) -> None:
    with pytest.raises(ValueError):
        mapper.map_matchup(roster_matchup_raw, week=10, user_team_id=999)


# --- historical (completed-week) boxscore (task 9.4) ------------------------------------


def test_map_roster_resolves_actual_points_for_a_completed_past_week(
    completed_week5_raw: dict,
) -> None:
    """A player's `stats[]` can carry entries for more than one scoringPeriodId (e.g. a
    fixture built to also exercise a *different* week's boxscore) — `map_roster` must
    pick the one matching the requested `week`, not just the first entry in the list."""
    slots = mapper.map_roster(completed_week5_raw, week=5)
    josh_allen = next(s for s in slots if s.player.name == "Josh Allen")

    assert josh_allen.week == 5
    assert josh_allen.actual_points == 22.4  # week 5's actual, not week 10's 99.9 decoy
    assert josh_allen.proj_points == 19.8


def test_map_matchup_marks_a_completed_past_week_as_complete(completed_week5_raw: dict) -> None:
    matchup, slots = mapper.map_matchup(completed_week5_raw, week=5, user_team_id=2)

    assert matchup.week == 5
    assert matchup.is_complete is True  # winner == "HOME", not "UNDECIDED"
    assert matchup.home_score == 101.4
    assert matchup.away_score == 90.0

    qb_slot = next(s for s in slots if s.slot == "QB")
    assert qb_slot.home_player.name == "Josh Allen"
    assert qb_slot.home_pts == 22.4
    assert qb_slot.away_player.name == "Patrick Mahomes"
    assert qb_slot.away_pts == 20.1
