"""`backend/gridiron/services/draft_slot_plan.py` (task 6.4). Pure, no DB/HTTP."""

from backend.gridiron.services.draft_slot_plan import SlotPlanTarget, parse_slot_plan


def test_parses_single_pick_block() -> None:
    payload = {
        "pick_numbers": [1, 24, 25],
        "structural_note": "note",
        "pick_1": {"take": "Jahmyr Gibbs", "confidence": "high"},
    }
    entries = parse_slot_plan(payload)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.picks == (1,)
    assert entry.label == "Pick 1"
    assert entry.confidence == "high"
    assert entry.rule is None
    assert entry.avoid == ()
    assert entry.targets == (SlotPlanTarget(name="Jahmyr Gibbs", group=None),)


def test_parses_paired_pick_block_with_groups_and_avoid() -> None:
    payload = {
        "picks_24_25": {
            "group_a_wr": ["Nico Collins", "Malik Nabers"],
            "group_b_rb_or_te": ["Omarion Hampton", "Trey McBride"],
            "rule": "Take one from each group.",
            "avoid": ["Josh Jacobs"],
        }
    }
    entries = parse_slot_plan(payload)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.picks == (24, 25)
    assert entry.label == "Picks 24 & 25"
    assert entry.confidence is None
    assert entry.rule == "Take one from each group."
    assert entry.avoid == ("Josh Jacobs",)
    names_and_groups = {(t.name, t.group) for t in entry.targets}
    assert names_and_groups == {
        ("Nico Collins", "group_a_wr"),
        ("Malik Nabers", "group_a_wr"),
        ("Omarion Hampton", "group_b_rb_or_te"),
        ("Trey McBride", "group_b_rb_or_te"),
    }


def test_real_strategy_rules_payload_parses_both_blocks_sorted_by_first_pick() -> None:
    # The actual shape shipped in draft_board/strategy_rules.json's draft_slot_1_plan --
    # regression coverage against the real contract, not just a hand-built fixture.
    payload = {
        "pick_numbers": [1, 24, 25, 48, 49, 72, 73],
        "structural_note": "Picks 24 and 25 are back-to-back. Plan in pairs.",
        "pick_1": {"take": "Jahmyr Gibbs", "confidence": "high"},
        "picks_24_25": {
            "group_a_wr": ["Nico Collins", "Malik Nabers", "Zay Flowers", "Chris Olave"],
            "group_b_rb_or_te": [
                "Omarion Hampton",
                "Kenneth Walker III",
                "Kyren Williams",
                "Trey McBride",
            ],
            "rule": "Take one from each group. McBride at 25 is defensible because he will not "
            "last to 48.",
            "avoid": ["Josh Jacobs", "Jeremiyah Love", "Breece Hall"],
        },
    }
    entries = parse_slot_plan(payload)
    assert [e.picks for e in entries] == [(1,), (24, 25)]


def test_ignores_unrelated_top_level_keys() -> None:
    payload = {"pick_numbers": [1], "structural_note": "x", "something_else": {"x": 1}}
    assert parse_slot_plan(payload) == []


def test_missing_take_yields_empty_targets_not_a_crash() -> None:
    payload = {"pick_2": {"confidence": "low"}}
    entries = parse_slot_plan(payload)
    assert entries[0].targets == ()


def test_missing_groups_and_avoid_do_not_crash() -> None:
    payload = {"picks_10_11": {"rule": "only a rule, no groups"}}
    entries = parse_slot_plan(payload)
    assert entries[0].targets == ()
    assert entries[0].avoid == ()
    assert entries[0].rule == "only a rule, no groups"


def test_entries_sorted_by_first_pick_regardless_of_payload_key_order() -> None:
    payload = {
        "picks_48_49": {"group_a_wr": ["Later WR"]},
        "pick_1": {"take": "First"},
        "picks_24_25": {"group_a_wr": ["Mid WR"]},
    }
    entries = parse_slot_plan(payload)
    assert [e.picks[0] for e in entries] == [1, 24, 48]
