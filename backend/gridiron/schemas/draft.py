"""Draft Assistant response models (task 3.3). Every read endpoint in `api/draft.py`
wraps these in the shared `Envelope` (design.md D12), same as every other read route.
"""

from typing import Any

from pydantic import BaseModel


class CandidateOut(BaseModel):
    """The recommender's `Candidate` (board player or drafted-pool member), serialized."""

    name: str
    position: str
    nfl_team: str | None
    bye: int | None
    adp_rank: int | None
    overall_tier: int | None
    positional_tier: int | None
    risk_score: int | None
    unpriced_risk: bool
    flags: list[str]


class AnalystTakeOut(BaseModel):
    """One `analyst_takes` entry (task 6.3). `verified_accuracy` distinguishes a
    measured-accuracy analyst (`sources.json`'s tier_a_measured) from a
    popular-but-unverified one (tier_b_popular_unverified) -- the PlayerDetail UI must
    render this alongside the source, not just the source name alone."""

    source: str
    verified_accuracy: bool
    take: str
    detail: str | None = None


class BoardPlayerOut(CandidateOut):
    """The full board, one row per player, WITH drafted status (task 3.4's `/board`
    keeps drafted players visible-but-greyed rather than removing them)."""

    id: int
    adp: float | None
    adp_round: int | None
    risk: str | None
    rookie: bool
    out_for_season: bool
    note: str | None
    thesis: str | None
    take_in_round: str | None
    is_drafted: bool
    drafted_overall_pick: int | None = None
    drafted_by_team: str | None = None
    is_my_pick: bool = False

    # 6.3 -- full scouting content, previously loaded but not exposed by this endpoint.
    sleeper_category: str | None = None
    catalyst: str | None = None
    format_fit: str | None = None
    # Keyword-derived from note prose, NOT curated fact -- see PlayerDetail.tsx's
    # rendering, which labels these explicitly as a search aid rather than diagnosis
    # (e.g. Jahmyr Gibbs carries "mcl" because his note mentions backup Pacheco's MCL
    # sprain, not his own injury).
    injury_tags: list[str] = []
    analyst_takes: list[AnalystTakeOut] = []
    overall_tier_label: str | None = None
    positional_tier_label: str | None = None


class BoardData(BaseModel):
    players: list[BoardPlayerOut]


class PoolData(BaseModel):
    players: list[CandidateOut]


class DraftPickOut(BaseModel):
    id: int
    overall_pick: int
    round: int | None
    board_player_id: int | None
    espn_player_id: int | None
    player_name: str
    position: str | None
    drafted_by_team: str | None
    is_my_pick: bool
    source: str


class RosterSlotOut(BaseModel):
    """One starter slot, e.g. `"QB"`/`"RB1"`/`"RB2"`/`"FLEX1"`/`"FLEX2"`/`"DST"`. FLEX is
    emitted as two distinct entries rather than reusing `schemas.common.Slot` (no FLEX2
    there) -- `slot` here is display-only, not the fantasy-data-model contract."""

    slot: str
    position_group: str  # the underlying position this slot draws from, e.g. "RB" for FLEX
    filled: bool
    player: CandidateOut | None = None


class RosterData(BaseModel):
    starters: list[RosterSlotOut]
    bench: list[CandidateOut]
    bye_collisions: list["ByeCollisionOut"]


class SettingsConflictOut(BaseModel):
    field: str
    static_value: Any
    espn_value: Any | None
    resolved_value: Any
    confirmed_by_espn: bool
    note: str = ""


class DraftStateData(BaseModel):
    picks: list[DraftPickOut]
    current_overall_pick: int
    current_round: int
    picks_until_next: int | None
    my_upcoming_picks: list[int]
    roster: RosterData
    settings_conflicts: list[SettingsConflictOut]
    session_status: str | None
    league_teams: int
    draft_over: bool


class RecommendationOut(BaseModel):
    candidate: CandidateOut
    score: float
    components: dict[str, float]
    reason: str
    fired_rule_ids: list[str]


class TierAlarmOut(BaseModel):
    position: str
    tier: int
    remaining: int
    picks_until_next: int


class ByeCollisionOut(BaseModel):
    bye: int
    count: int
    players: list[str]


class PositionalRunOut(BaseModel):
    """6.1 -- a position currently "running": >= 4 of the last 8 picks landed there."""

    position: str
    count: int


class TurnPairOut(BaseModel):
    pick_a: int
    pick_b: int
    recommendation_a: RecommendationOut
    recommendation_b: RecommendationOut


class RecommendationsData(BaseModel):
    current_overall_pick: int
    picks_until_next: int | None
    shortlist: list[RecommendationOut]
    tier_alarms: list[TierAlarmOut]
    bye_collisions: list[ByeCollisionOut]
    positional_runs: list[PositionalRunOut]
    advisories: list[str]
    turn_pairs: list[TurnPairOut]


class RecordPickIn(BaseModel):
    player_name: str | None = None
    board_player_id: int | None = None
    is_my_pick: bool = False
    drafted_by_team: str | None = None
    overall_pick: int | None = None


class UndoResultData(BaseModel):
    undone: DraftPickOut | None


class CurrentPickIn(BaseModel):
    overall_pick: int


class CurrentPickData(BaseModel):
    current_overall_pick: int
    current_round: int
    picks_until_next: int | None


class SlotPlanTargetOut(BaseModel):
    """One named target within a slot-plan entry, recomputed against the LIVE draft
    (task 6.4) -- never rendered as static text. `group` is the source block's own key
    (e.g. `group_a_wr`) for a paired-picks entry, `None` for a single-target pick."""

    name: str
    group: str | None = None
    sniped: bool
    drafted_by_me: bool
    drafted_by_team: str | None = None
    still_available: bool


class SlotPlanEntryOut(BaseModel):
    picks: list[int]
    label: str
    confidence: str | None = None
    rule: str | None = None
    avoid: list[str] = []
    targets: list[SlotPlanTargetOut]


class SlotPlanData(BaseModel):
    """`board_heuristics._draft_slot_1_plan`, task 6.4. `applicable` is false whenever
    `user_draft_slot != 1` -- its pick numbers and back-to-back reasoning are ONLY valid
    at slot 1 in a 12-team snake, so the frontend must not present it as usable
    otherwise (still returned, not withheld, so a UI that wants to explain WHY can)."""

    applicable: bool
    user_draft_slot: int
    structural_note: str | None = None
    pick_numbers: list[int]
    entries: list[SlotPlanEntryOut]
    # Pick numbers from `pick_numbers` with no matching `pick_<N>`/`picks_<A>_<B>` block
    # in the source payload yet (today: 48, 49, 72, 73 -- see draft_slot_plan.py).
    unplanned_pick_numbers: list[int]


class EspnMatchCandidateOut(BaseModel):
    """One ESPN player universe entry offered as a possible match (task 4.5)."""

    espn_player_id: int
    full_name: str
    position: str
    nfl_team: str
    is_dst: bool


class BoardMatchOut(BaseModel):
    """One board player's match state against the ESPN universe. `candidates` is only
    ever non-empty for a row below the 0.9 confidence gate -- see
    `services/draft_matches.py`."""

    board_player_name: str
    espn_player_id: int | None
    match_method: str
    match_confidence: float
    candidates: list[EspnMatchCandidateOut] = []


class MatchesData(BaseModel):
    """4.5 -- every board entry's match state, plus the summary counts the UI gates
    live-mode readiness on (`below_threshold_count`, confidence < 0.9)."""

    matches: list[BoardMatchOut]
    method_counts: dict[str, int]
    below_threshold_count: int


class MatchOverrideIn(BaseModel):
    """Body for `POST /api/draft/matches/{name}`. `espn_player_id` omitted or explicit
    `null` both mean "explicitly no ESPN match" -- a hand-maintained override recording
    that this board player has no ESPN counterpart, which still counts as resolved
    (`match_method="override"`, `match_confidence=1.0`) and survives re-import like any
    other override."""

    espn_player_id: int | None = None


RosterData.model_rebuild()
