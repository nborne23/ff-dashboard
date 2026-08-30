"""Shared literals and the response envelope, per design.md D12.

`Envelope[T]` is the wrapper every read endpoint returns:
`{ data: T, meta: { live_state, as_of, next_refresh_at, platforms } }`.
"""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

Platform = Literal["yahoo", "espn"]
LiveState = Literal["live", "game_day", "off_day"]

# The internal roster/matchup slot vocabulary (design.md D12).
#
# Repeatable starter slots are NUMBERED by order of appearance in the roster, the same
# rule that already governs RB1/RB2 and WR1/WR2. Real leagues run more than one flex —
# a three-flex lineup is common — and a single unnumbered `FLEX` silently collapsed
# them: the mappers key their starter maps by slot label, so two of three flex starters
# were overwritten, dropping their points from the matchup projection and their rows
# from the head-to-head table.
#
# `"FLEX"` (unnumbered) is retained as a LEGACY value. The mappers no longer emit it,
# but this Literal is validated on READ — `_roster_slot_schema` builds a `RosterSlot`
# from each persisted row — so dropping it would make every read of an already-synced
# league fail until a refresh rewrote its rows.
#
# The numbered forms are bounded. A lineup exceeding them raises during mapping rather
# than silently mislabelling a player, matching the fail-loud rule `UnknownSlotError`
# already applies to unrecognized platform slot codes.
Slot = Literal[
    "QB",
    "RB1",
    "RB2",
    "WR1",
    "WR2",
    "TE",
    "FLEX",  # legacy — persisted by earlier syncs; no longer emitted
    "FLEX1",
    "FLEX2",
    "FLEX3",
    "FLEX4",
    "OP1",  # superflex / "offensive player"
    "OP2",
    "K",
    "DST",
    "BN",
    "IR",
]


class PlatformStatus(BaseModel):
    """`meta.platforms[platform]` — `{ ok: boolean; error?: string }`."""

    ok: bool
    error: str | None = None


class Meta(BaseModel):
    live_state: LiveState
    as_of: datetime
    next_refresh_at: datetime
    platforms: dict[Platform, PlatformStatus]


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta
