import pytest

from backend.gridiron.platforms.espn.slot_table import UnknownSlotError, espn_slot_name


@pytest.mark.parametrize(
    ("lineup_slot_id", "expected"),
    [
        (0, "QB"),
        (2, "RB"),
        (4, "WR"),
        (6, "TE"),
        (23, "FLEX"),
        (16, "DST"),
        (17, "K"),
        (20, "BN"),
        (21, "IR"),
    ],
)
def test_known_ids_map_to_expected_names(lineup_slot_id: int, expected: str) -> None:
    assert espn_slot_name(lineup_slot_id) == expected


def test_unknown_id_raises_unknown_slot_error() -> None:
    with pytest.raises(UnknownSlotError):
        espn_slot_name(9999)


def test_unknown_slot_error_carries_the_offending_id() -> None:
    try:
        espn_slot_name(9999)
    except UnknownSlotError as exc:
        assert exc.lineup_slot_id == 9999
    else:
        pytest.fail("expected UnknownSlotError")
