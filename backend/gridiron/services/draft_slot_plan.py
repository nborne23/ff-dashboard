"""6.4 -- parses `board_heuristics`' `_draft_slot_1_plan` payload (the hand-authored,
pick-by-pick plan for drafting from slot 1 in a 12-team snake -- see
`draft_board/strategy_rules.json`'s `draft_slot_1_plan` block) into structured entries.

Pure (no DB, no HTTP), same discipline as `draft_recommender.py`: the payload's shape is
walked generically by key pattern (`pick_<N>` for a single-target pick, `picks_<A>_<B>`
for a paired-picks block with named target groups) rather than hardcoding today's two
populated blocks (`pick_1`, `picks_24_25`) -- so if a later board update adds
`picks_48_49`/`picks_72_73` (both already listed in `pick_numbers` but NOT populated as
of this board), this keeps working without a code change. `api/draft.py` is the caller
with DB access; it fills in each target's live sniped/still-available status against
`draft_picks`, which this module has no way to know.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_PICK_KEY_RE = re.compile(r"^pick_(\d+)$")
_PICKS_KEY_RE = re.compile(r"^picks_(\d+)_(\d+)$")

# Reserved keys inside a `picks_<A>_<B>` block that are NOT a named-target group (every
# other list-valued key is treated as one, e.g. `group_a_wr` / `group_b_rb_or_te`).
_NON_GROUP_KEYS = ("rule", "avoid")


@dataclass(frozen=True)
class SlotPlanTarget:
    name: str
    # The block's own group key (e.g. "group_a_wr"), or None for a single-target
    # `pick_<N>` entry that has no groups at all.
    group: str | None = None


@dataclass(frozen=True)
class SlotPlanEntry:
    picks: tuple[int, ...]
    label: str
    confidence: str | None
    rule: str | None
    avoid: tuple[str, ...]
    targets: tuple[SlotPlanTarget, ...]


def parse_slot_plan(payload: dict[str, Any]) -> list[SlotPlanEntry]:
    """Walk every top-level key in the `_draft_slot_1_plan` payload, emitting one
    `SlotPlanEntry` per `pick_<N>` or `picks_<A>_<B>` block found (ignoring
    `pick_numbers`/`structural_note` and anything else that doesn't match either
    pattern). Returned sorted by each entry's first pick number."""
    entries: list[SlotPlanEntry] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue

        single = _PICK_KEY_RE.match(key)
        if single:
            pick_num = int(single.group(1))
            take = value.get("take")
            targets = (SlotPlanTarget(name=take),) if isinstance(take, str) and take else ()
            entries.append(
                SlotPlanEntry(
                    picks=(pick_num,),
                    label=f"Pick {pick_num}",
                    confidence=value.get("confidence"),
                    rule=None,
                    avoid=(),
                    targets=targets,
                )
            )
            continue

        paired = _PICKS_KEY_RE.match(key)
        if paired:
            pick_a, pick_b = int(paired.group(1)), int(paired.group(2))
            targets = []
            for group_key, group_val in value.items():
                if group_key in _NON_GROUP_KEYS or not isinstance(group_val, list):
                    continue
                targets.extend(
                    SlotPlanTarget(name=name, group=group_key)
                    for name in group_val
                    if isinstance(name, str)
                )
            avoid = value.get("avoid")
            entries.append(
                SlotPlanEntry(
                    picks=(pick_a, pick_b),
                    label=f"Picks {pick_a} & {pick_b}",
                    confidence=None,
                    rule=value.get("rule") if isinstance(value.get("rule"), str) else None,
                    avoid=tuple(avoid) if isinstance(avoid, list) else (),
                    targets=tuple(targets),
                )
            )

    entries.sort(key=lambda e: e.picks[0])
    return entries
