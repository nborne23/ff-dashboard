"""ESPN `lineupSlotId` -> ESPN's own slot-name vocabulary.

ESPN's fantasy API represents each roster entry's lineup slot as an integer
(`lineupSlotId`). This module is a static lookup from that integer to ESPN's
documented slot name, modeled on the `LINEUP_SLOT_MAP` table used by the
`cwendt94/espn-api` project (the reference implementation cited in design.md D1).

This is an *intermediate* vocabulary, not the internal `schemas.common.Slot`
literal — `espn.mapper` is responsible for translating these names into the
internal vocabulary (including numbering duplicates like `RB` -> `RB1`/`RB2`
by roster order). Keeping this table ESPN-shaped (rather than pre-translating
here) means a change to ESPN's ids only ever touches this one file.

Per the fantasy-data-model spec's "Mapper purity" scenario, unknown ids must
fail loud rather than silently drop a player — hence `UnknownSlotError` instead
of a `.get(..., default)` lookup.
"""


class UnknownSlotError(Exception):
    """Raised when an ESPN `lineupSlotId` isn't in `LINEUP_SLOT_MAP`.

    Defined locally (not in `backend/gridiron/errors.py`) so this module has
    zero dependencies outside the standard library — it's pure lookup data.
    """

    def __init__(self, lineup_slot_id: int) -> None:
        self.lineup_slot_id = lineup_slot_id
        super().__init__(f"unknown ESPN lineupSlotId: {lineup_slot_id!r}")


# Modeled on espn-api's LINEUP_SLOT_MAP (espn_api/football/constant.py). Values
# for the offense-only slots this project supports (QB/RB/WR/TE/FLEX/DST/K/BN/IR)
# are normalized to match the internal `Slot` vocabulary directly (e.g. `20 -> "BN"`,
# not ESPN's raw `"BE"`) so `mapper.py` only has to special-case the numbered
# duplicates (RB -> RB1/RB2, WR -> WR1/WR2). IDP / kicker-adjacent / rarely-used
# slots are kept at ESPN's own label since no internal `Slot` value exists for them;
# `mapper.map_roster` raises if one of those is ever encountered in a roster entry.
LINEUP_SLOT_MAP: dict[int, str] = {
    0: "QB",
    1: "TQB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    8: "DT",
    9: "DE",
    10: "LB",
    11: "DL",
    12: "CB",
    13: "S",
    14: "DB",
    15: "DP",
    16: "DST",
    17: "K",
    18: "P",
    19: "HC",
    20: "BN",
    21: "IR",
    22: "UNKNOWN",
    23: "FLEX",
    24: "EDR",
    25: "REC_FLEX",
}


def espn_slot_name(lineup_slot_id: int) -> str:
    """Look up ESPN's slot name for `lineup_slot_id`, raising `UnknownSlotError` on a miss."""
    try:
        return LINEUP_SLOT_MAP[lineup_slot_id]
    except KeyError as exc:
        raise UnknownSlotError(lineup_slot_id) from exc
