"""`yahoo/mapper.py` — pure raw-JSON -> normalized-entity mappers, tested against fixtures."""

import json
from pathlib import Path

import pytest

from backend.gridiron import schemas
from backend.gridiron.platforms.yahoo import mapper
from backend.gridiron.platforms.yahoo._yahoo_json import collection_items, find_subresource

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "yahoo"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# --- map_league ---------------------------------------------------------------------------


def test_map_league_returns_normalized_league() -> None:
    raw = load_fixture("leagues.json")
    games = collection_items(raw["fantasy_content"]["users"]["0"]["user"][1]["games"])
    leagues_root = find_subresource(games[0]["game"], "leagues")
    league_item = collection_items(leagues_root)[0]

    league = mapper.map_league(league_item)

    assert league == schemas.League(
        id="yahoo:461.l.123456",
        platform="yahoo",
        platform_id="461.l.123456",
        name="The League of Extraordinary Gentlemen",
        season=2025,
        team_count=10,
        scoring_type="standard",
        current_week=14,
    )


def test_map_league_translates_scoring_type_point_to_ppr() -> None:
    raw = load_fixture("leagues.json")
    games = collection_items(raw["fantasy_content"]["users"]["0"]["user"][1]["games"])
    leagues_root = find_subresource(games[0]["game"], "leagues")
    league_item = collection_items(leagues_root)[1]

    league = mapper.map_league(league_item)

    assert league.name == "Dynasty Warriors"
    assert league.scoring_type == "ppr"


def test_map_league_unrecognized_scoring_type_falls_back_to_custom() -> None:
    raw = load_fixture("leagues.json")
    games = collection_items(raw["fantasy_content"]["users"]["0"]["user"][1]["games"])
    leagues_root = find_subresource(games[0]["game"], "leagues")
    league_item = collection_items(leagues_root)[0]
    league_item["league"][0]["scoring_type"] = "something-new"

    league = mapper.map_league(league_item)

    assert league.scoring_type == "custom"


def test_map_league_missing_field_raises_mapper_error() -> None:
    broken = {"league": [{"league_key": "461.l.1"}]}  # missing name/season/etc.

    with pytest.raises(mapper.MapperError):
        mapper.map_league(broken)


# --- map_team ------------------------------------------------------------------------------


def test_map_team_owned_team_sets_is_user_team_and_manager_name() -> None:
    raw = load_fixture("teams.json")
    teams_root = find_subresource(raw["fantasy_content"]["league"], "teams")
    team_item = collection_items(teams_root)[0]

    team = mapper.map_team(team_item, league_id="yahoo:461.l.123456")

    assert team.id == "yahoo:461.l.123456.t.1"
    assert team.league_id == "yahoo:461.l.123456"
    assert team.name == "Gridiron Gurus"
    assert team.manager_name == "Nick"
    assert team.is_user_team is True
    assert team.accent_color.startswith("#")
    assert len(team.accent_color) == 7


def test_map_team_unowned_team_sets_is_user_team_false() -> None:
    raw = load_fixture("teams.json")
    teams_root = find_subresource(raw["fantasy_content"]["league"], "teams")
    team_item = collection_items(teams_root)[1]

    team = mapper.map_team(team_item, league_id="yahoo:461.l.123456")

    assert team.is_user_team is False
    assert team.manager_name == "Sam"


def test_map_team_accent_color_is_deterministic() -> None:
    raw = load_fixture("teams.json")
    teams_root = find_subresource(raw["fantasy_content"]["league"], "teams")
    team_item = collection_items(teams_root)[0]

    first = mapper.map_team(team_item, league_id="yahoo:461.l.123456")
    second = mapper.map_team(team_item, league_id="yahoo:461.l.123456")

    assert first.accent_color == second.accent_color


def test_map_team_missing_field_raises_mapper_error() -> None:
    broken = {"team": [[{"team_key": "461.l.1.t.1"}]]}  # missing name

    with pytest.raises(mapper.MapperError):
        mapper.map_team(broken, league_id="yahoo:461.l.1")


# --- map_roster ----------------------------------------------------------------------------


def test_map_roster_returns_all_slots_with_translated_codes() -> None:
    raw = load_fixture("roster.json")

    slots = mapper.map_roster(raw, week=14)

    assert len(slots) == 11
    slot_codes = [s.slot for s in slots]
    assert slot_codes == [
        "QB",
        "RB1",
        "RB2",
        "WR1",
        "WR2",
        "TE",
        "FLEX1",
        "K",
        "DST",
        "BN",
        "IR",
    ]
    assert all(s.team_id == "yahoo:461.l.123456.t.1" for s in slots)
    assert all(s.week == 14 for s in slots)


def test_map_roster_maps_player_fields_and_points() -> None:
    raw = load_fixture("roster.json")

    slots = mapper.map_roster(raw, week=14)
    qb = slots[0]

    assert qb.player.id == "yahoo:461.p.30123"
    assert qb.player.name == "Patrick Mahomes"
    assert qb.player.position == "QB"
    assert qb.player.nfl_team == "KC"
    assert qb.player.bye_week == 6
    assert qb.player.injury_status == "ACTIVE"
    assert qb.actual_points == 27.40
    assert qb.proj_points == 22.10


def test_map_roster_maps_defense_position_to_dst() -> None:
    raw = load_fixture("roster.json")

    slots = mapper.map_roster(raw, week=14)
    defense = next(s for s in slots if s.slot == "DST")

    assert defense.player.position == "DST"
    assert defense.player.nfl_team == "SF"


def test_map_roster_maps_injury_status() -> None:
    raw = load_fixture("roster.json")

    slots = mapper.map_roster(raw, week=14)
    questionable = next(s for s in slots if s.player.name == "CeeDee Lamb")
    injured_reserve = next(s for s in slots if s.player.name == "Nick Chubb")

    assert questionable.player.injury_status == "Q"
    assert injured_reserve.player.injury_status == "IR"
    assert injured_reserve.slot == "IR"


def test_map_roster_unknown_slot_code_raises_mapper_error() -> None:
    raw = load_fixture("roster.json")
    raw["fantasy_content"]["team"][1]["roster"]["0"]["players"]["0"]["player"][1][
        "selected_position"
    ][2]["position"] = "SUPERFLEX"

    with pytest.raises(mapper.MapperError, match="SUPERFLEX"):
        mapper.map_roster(raw, week=14)


def test_map_roster_unknown_position_raises_mapper_error() -> None:
    raw = load_fixture("roster.json")
    raw["fantasy_content"]["team"][1]["roster"]["0"]["players"]["0"]["player"][0][4][
        "display_position"
    ] = "LB"

    with pytest.raises(mapper.MapperError, match="LB"):
        mapper.map_roster(raw, week=14)


# --- map_matchup ---------------------------------------------------------------------------


def test_map_matchup_returns_normalized_matchup() -> None:
    raw = load_fixture("matchup.json")

    matchup = mapper.map_matchup(raw, week=14)

    assert matchup == schemas.Matchup(
        id="yahoo:461.l.123456.mu.14",
        league_id="yahoo:461.l.123456",
        week=14,
        home_team_id="yahoo:461.l.123456.t.1",
        away_team_id="yahoo:461.l.123456.t.2",
        home_score=88.24,
        away_score=76.10,
        home_proj=104.50,
        away_proj=95.20,
        is_complete=False,
    )


def test_map_matchup_postevent_status_marks_complete() -> None:
    raw = load_fixture("matchup.json")
    raw["fantasy_content"]["team"][1]["matchups"]["0"]["matchup"]["status"] = "postevent"

    matchup = mapper.map_matchup(raw, week=14)

    assert matchup.is_complete is True


def test_map_matchup_missing_teams_raises_mapper_error() -> None:
    raw = load_fixture("matchup.json")
    raw["fantasy_content"]["team"][1]["matchups"]["0"]["matchup"]["teams"] = {"count": 0}

    with pytest.raises(mapper.MapperError):
        mapper.map_matchup(raw, week=14)


def test_translate_slot_numbers_repeated_flex_codes() -> None:
    """Yahoo's flex code is `W/R/T`, and a lineup may hold several. They are renamed AND
    numbered (FLEX1/FLEX2/...) for the same reason the ESPN side numbers them: the
    matchup pairing keys by slot label, so one shared label collapses the lineup."""
    counters: dict[str, int] = {}

    assert mapper._translate_slot("W/R/T", counters) == "FLEX1"
    assert mapper._translate_slot("W/R/T", counters) == "FLEX2"
    assert mapper._translate_slot("W/R/T", counters) == "FLEX3"


def test_translate_slot_maps_superflex_to_numbered_op() -> None:
    counters: dict[str, int] = {}

    assert mapper._translate_slot("Q/W/R/T", counters) == "OP1"
    assert mapper._translate_slot("Q/W/R/T", counters) == "OP2"


def test_translate_slot_counters_are_independent_per_slot_family() -> None:
    counters: dict[str, int] = {}

    assert mapper._translate_slot("RB", counters) == "RB1"
    assert mapper._translate_slot("W/R/T", counters) == "FLEX1"
    assert mapper._translate_slot("RB", counters) == "RB2"
    assert mapper._translate_slot("W/R/T", counters) == "FLEX2"
