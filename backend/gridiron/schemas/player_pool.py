"""`PlayerPoolEntry` / `WaiverCandidate` — add-player-pool's normalized entities."""

from typing import Literal

from pydantic import BaseModel

from backend.gridiron.schemas.players import Player

PoolStatus = Literal["FREEAGENT", "WAIVERS", "ONTEAM"]


class PlayerPoolEntry(BaseModel):
    """One player's availability and season projection within one league.

    `ONTEAM` is a real member of `PoolStatus`, not defensive slack: the ingestion
    filter requests rostered players deliberately so an incumbent starter has a
    season projection to be compared against (design D7).
    """

    league_id: str
    player: Player
    status: PoolStatus
    on_team_id: str | None
    percent_owned: float
    percent_started: float
    # None when ESPN published no season projection. Distinct from 0.0, which is a
    # genuine value for a player projected to score nothing (design D2).
    season_proj_points: float | None


class WaiverCandidate(PlayerPoolEntry):
    """A pool entry presented as claimable, with the comparison that makes it
    actionable.

    `status` is inherited and is always `FREEAGENT` or `WAIVERS` here in practice —
    `ONTEAM` rows are ingested so an incumbent starter has a season projection to be
    compared against, but are never listed as candidates. That exclusion lives in
    `get_waivers`, not in the type.
    """

    # The candidate's season projection minus that of the lowest-projected starter
    # the user rosters at a slot this player is eligible for. None — never 0.0 —
    # when either side lacks a projection or no eligible starter exists.
    #
    # Both operands are SEASON-scoped. `RosterSlot.proj_points` is a weekly number
    # (21.57 vs 364.86 for the same player) and must never be an operand here.
    delta_vs_worst_starter: float | None
    # ESPN's UNNUMBERED slot vocabulary, straight from `LINEUP_SLOT_MAP`: "QB", "RB",
    # "WR", "TE", "FLEX", "RB/WR", "WR/TE", "REC_FLEX", "OP", "K", "DST", ...
    #
    # Deliberately NOT the internal `Slot` type. `Slot` numbers its positions
    # (`RB1`, `RB2`) from per-roster counters in `_internal_slot`, and a pool player
    # is on no roster — there is no counter context, so no basis for RB1 vs RB2.
    # Used to pick the comparison starter: a FLEX-eligible RB is measured against
    # the weakest of the RB/FLEX starters actually rostered.
    eligible_slots: list[str]


class WaiversData(BaseModel):
    """Payload of `GET /api/teams/{team_id}/waivers`."""

    team_id: str
    league_id: str
    week: int
    candidates: list[WaiverCandidate]
