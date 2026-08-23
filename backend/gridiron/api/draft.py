"""`/api/draft*` — the Draft Assistant read/write API (task 3.4).

Every read endpoint returns the `Envelope` (design.md D12), same as `api/teams.py`.
Writes (`POST /picks`, `DELETE /picks/last`, `PUT /current-pick`) return the bare
payload, matching the house convention in `api/leagues.py`/`api/connections.py` --
`Envelope` wraps read freshness metadata that a write response has no use for.

This must be fully usable with ZERO ESPN integration (phase 5 owns arm/disarm/polling):
every endpoint here only ever reads/writes `board_players` / `draft_picks` /
`draft_sessions` via `services/draft_state.py`.
"""

import dataclasses
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.errors import DraftPickConflictError
from backend.gridiron.models import BoardHeuristic, BoardPlayer, BoardTier
from backend.gridiron.schemas import Envelope
from backend.gridiron.schemas.draft import (
    AnalystTakeOut,
    BoardData,
    BoardMatchOut,
    BoardPlayerOut,
    ByeCollisionOut,
    CandidateOut,
    CurrentPickData,
    CurrentPickIn,
    DraftPickOut,
    DraftStateData,
    EspnMatchCandidateOut,
    MatchesData,
    MatchOverrideIn,
    PoolData,
    PositionalRunOut,
    RecommendationOut,
    RecommendationsData,
    RecordPickIn,
    RosterData,
    RosterSlotOut,
    SettingsConflictOut,
    SlotPlanData,
    SlotPlanEntryOut,
    SlotPlanTargetOut,
    TierAlarmOut,
    TurnPairOut,
    UndoResultData,
)
from backend.gridiron.services import differ, draft_matches, draft_state, fantasy_service
from backend.gridiron.services.draft_pick_math import round_for_pick, snake_pick_numbers, turn_pairs
from backend.gridiron.services.draft_recommender import (
    Candidate,
    LeagueShape,
    Recommendation,
    bye_collisions,
    elite_te_window_advisories,
    handcuff_advisories,
    no_kicker_advisory,
    positional_runs,
    recommend,
    recommend_pair,
    tier_break_alarms,
)
from backend.gridiron.services.draft_slot_plan import parse_slot_plan

router = APIRouter(prefix="/api/draft", tags=["draft"])

CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"

# Deterministic starter-slot fill order (task 3.10: FLEX rendered as its own slots,
# never a kicker slot -- this league's static config carries K:0, so the loop below
# simply never emits one).
_DEDICATED_ORDER = ("QB", "RB", "WR", "TE", "DST", "K")

# 6.1: the recommender's positional-run detection needs the trailing 8 picks
# (draft_recommender._RUN_WINDOW) to ever fire, so this must be >= 8.
RECENT_PICKS_WINDOW = 8


async def _envelope(session: AsyncSession, data) -> Envelope:
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    return Envelope(data=data, meta=meta)


def _candidate_out(c: Candidate) -> CandidateOut:
    return CandidateOut(
        name=c.name,
        position=c.position,
        nfl_team=c.nfl_team,
        bye=c.bye,
        adp_rank=c.adp_rank,
        overall_tier=c.overall_tier,
        positional_tier=c.positional_tier,
        risk_score=c.risk_score,
        unpriced_risk=c.unpriced_risk,
        flags=list(c.flags),
    )


def _pick_out(pick) -> DraftPickOut:
    return DraftPickOut(
        id=pick.id,
        overall_pick=pick.overall_pick,
        round=pick.round,
        board_player_id=pick.board_player_id,
        espn_player_id=pick.espn_player_id,
        player_name=pick.player_name,
        position=pick.position,
        drafted_by_team=pick.drafted_by_team,
        is_my_pick=pick.is_my_pick,
        source=pick.source,
    )


def _rec_out(rec: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        candidate=_candidate_out(rec.candidate),
        score=rec.score,
        components=dict(rec.components),
        reason=rec.reason,
        fired_rule_ids=list(rec.fired_rule_ids),
    )


def _assign_roster_slots(
    roster: list[Candidate], league: LeagueShape
) -> tuple[list[RosterSlotOut], list[Candidate], list[Candidate]]:
    """Fill / unfilled starter slots from the league's real roster shape (task 3.10):
    dedicated positions first (earliest-drafted player at that position claims the
    slot -- `roster` arrives in draft order from `draft_state.my_roster`), then
    whatever's left over that's flex-eligible fills FLEX slots (each rendered as its
    own numbered entry, e.g. `FLEX1`/`FLEX2` -- `schemas.common.Slot` has no FLEX2, so
    this is display-only, not that contract). Returns (starter slots, the players who
    filled them -- the "projected starters" bye-collision math wants, NOT the whole
    roster -- and the bench: everyone else).
    """
    remaining = list(roster)
    slots: list[RosterSlotOut] = []
    starter_players: list[Candidate] = []

    for pos in _DEDICATED_ORDER:
        count = league.starters.get(pos, 0)
        if count <= 0:
            continue
        pos_candidates = [c for c in remaining if c.position == pos]
        for i in range(count):
            label = f"{pos}{i + 1}" if count > 1 else pos
            if i < len(pos_candidates):
                player = pos_candidates[i]
                remaining.remove(player)
                starter_players.append(player)
                slots.append(
                    RosterSlotOut(
                        slot=label, position_group=pos, filled=True, player=_candidate_out(player)
                    )
                )
            else:
                slots.append(RosterSlotOut(slot=label, position_group=pos, filled=False))

    flex_count = league.starters.get("FLEX", 0)
    flex_candidates = [c for c in remaining if c.position in league.flex_eligible]
    for i in range(flex_count):
        label = f"FLEX{i + 1}" if flex_count > 1 else "FLEX"
        if i < len(flex_candidates):
            player = flex_candidates[i]
            remaining.remove(player)
            starter_players.append(player)
            slots.append(
                RosterSlotOut(
                    slot=label, position_group="FLEX", filled=True, player=_candidate_out(player)
                )
            )
        else:
            slots.append(RosterSlotOut(slot=label, position_group="FLEX", filled=False))

    return slots, starter_players, remaining


async def _league_context(
    session: AsyncSession,
) -> tuple[LeagueShape, list[SettingsConflictOut], list[int], int, int | None]:
    """Shared setup every state/recommendations handler needs: resolved league shape,
    its settings-conflict list (serialized), this user's full snake-draft pick list,
    the current overall pick, and picks-until-next (`None` when the draft's past the
    user's last scheduled pick -- see `draft_state.picks_until_next`)."""
    league_shape, conflicts = await draft_state.resolve_league_shape(session)
    conflicts_out = [SettingsConflictOut(**dataclasses.asdict(c)) for c in conflicts]
    my_picks = snake_pick_numbers(league_shape.teams, league_shape.slot, league_shape.rounds)
    current_pick = await draft_state.get_current_overall_pick(session)
    picks_until = draft_state.picks_until_next(current_pick, my_picks)
    return league_shape, conflicts_out, my_picks, current_pick, picks_until


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def _tier_label_lookup(session: AsyncSession) -> dict[tuple[str, str | None, int], str]:
    """6.3 -- `board_tiers` keyed `(scope, position, tier)` -> `label`, so `/board` can
    attach the overall AND positional tier labels PlayerDetail.tsx needs alongside the
    bare tier numbers `CandidateOut` already carries."""
    result = await session.execute(select(BoardTier))
    return {(t.scope, t.position, t.tier): t.label for t in result.scalars().all()}


def _decode_json_list(raw: str | None) -> list:
    return json.loads(raw) if raw else []


@router.get("/board", response_model=Envelope[BoardData])
async def get_board(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[BoardData]:
    response.headers["Cache-Control"] = CACHE_CONTROL

    picks = await draft_state.list_picks(session)
    pick_by_board_id = {p.board_player_id: p for p in picks if p.board_player_id is not None}
    tier_labels = await _tier_label_lookup(session)

    result = await session.execute(
        select(BoardPlayer).order_by(BoardPlayer.adp_rank.is_(None), BoardPlayer.adp_rank)
    )
    players = []
    for bp in result.scalars().all():
        candidate = draft_state.to_candidate(bp)
        pick = pick_by_board_id.get(bp.id)
        analyst_takes = [AnalystTakeOut(**take) for take in _decode_json_list(bp.analyst_takes)]
        players.append(
            BoardPlayerOut(
                **_candidate_out(candidate).model_dump(),
                id=bp.id,
                adp=bp.adp,
                adp_round=bp.adp_round,
                risk=bp.risk,
                rookie=bp.rookie,
                out_for_season=bp.out_for_season,
                note=bp.note,
                thesis=bp.thesis,
                take_in_round=bp.take_in_round,
                is_drafted=pick is not None,
                drafted_overall_pick=pick.overall_pick if pick is not None else None,
                drafted_by_team=pick.drafted_by_team if pick is not None else None,
                is_my_pick=pick.is_my_pick if pick is not None else False,
                sleeper_category=bp.sleeper_category,
                catalyst=bp.catalyst,
                format_fit=bp.format_fit,
                injury_tags=_decode_json_list(bp.injury_tags),
                analyst_takes=analyst_takes,
                overall_tier_label=(
                    tier_labels.get(("overall", None, bp.overall_tier))
                    if bp.overall_tier is not None
                    else None
                ),
                positional_tier_label=(
                    tier_labels.get(("positional", bp.position, bp.positional_tier))
                    if bp.positional_tier is not None
                    else None
                ),
            )
        )
    return await _envelope(session, BoardData(players=players))


@router.get("/pool", response_model=Envelope[PoolData])
async def get_pool(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[PoolData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    pool = await draft_state.undrafted_pool(session)
    return await _envelope(session, PoolData(players=[_candidate_out(c) for c in pool]))


@router.get("/state", response_model=Envelope[DraftStateData])
async def get_state(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[DraftStateData]:
    response.headers["Cache-Control"] = CACHE_CONTROL

    league_shape, conflicts_out, my_picks, current_pick, picks_until = await _league_context(
        session
    )
    picks = await draft_state.list_picks(session)
    roster = await draft_state.my_roster(session)
    slots, starter_players, bench = _assign_roster_slots(roster, league_shape)
    bye_collisions_out = [
        ByeCollisionOut(bye=b.bye, count=b.count, players=list(b.players))
        for b in bye_collisions(starter_players)
    ]
    session_status = await draft_state.get_session_status(session)

    data = DraftStateData(
        picks=[_pick_out(p) for p in picks],
        current_overall_pick=current_pick,
        current_round=round_for_pick(current_pick, league_shape.teams),
        picks_until_next=picks_until,
        my_upcoming_picks=[p for p in my_picks if p >= current_pick],
        roster=RosterData(
            starters=slots,
            bench=[_candidate_out(c) for c in bench],
            bye_collisions=bye_collisions_out,
        ),
        settings_conflicts=conflicts_out,
        session_status=session_status,
        league_teams=league_shape.teams,
        draft_over=picks_until is None,
    )
    return await _envelope(session, data)


@router.get("/recommendations", response_model=Envelope[RecommendationsData])
async def get_recommendations(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[RecommendationsData]:
    response.headers["Cache-Control"] = CACHE_CONTROL

    league_shape, _conflicts_out, my_picks, current_pick, picks_until = await _league_context(
        session
    )
    pool = await draft_state.undrafted_pool(session)
    roster = await draft_state.my_roster(session)
    recent = await draft_state.recent_picks(session, limit=RECENT_PICKS_WINDOW)

    shortlist: list[RecommendationOut] = []
    tier_alarms_out: list[TierAlarmOut] = []
    if picks_until is not None:
        recs = recommend(pool, roster, league_shape, current_pick, picks_until, recent)
        shortlist = [_rec_out(r) for r in recs]
        tier_alarms_out = [
            TierAlarmOut(
                position=a.position,
                tier=a.tier,
                remaining=a.remaining,
                picks_until_next=a.picks_until_next,
            )
            for a in tier_break_alarms(pool, picks_until)
        ]

    _slots, starter_players, _bench = _assign_roster_slots(roster, league_shape)
    bye_collisions_out = [
        ByeCollisionOut(bye=b.bye, count=b.count, players=list(b.players))
        for b in bye_collisions(starter_players)
    ]
    positional_runs_out = [
        PositionalRunOut(position=pos, count=count)
        for pos, count in sorted(positional_runs(recent).items())
    ]

    advisories: list[str] = []
    kicker_note = no_kicker_advisory(league_shape)
    if kicker_note:
        advisories.append(kicker_note)
    advisories.extend(elite_te_window_advisories(pool, current_pick))
    advisories.extend(handcuff_advisories(roster))

    turn_pairs_out: list[TurnPairOut] = []
    if picks_until is not None:
        next_pick = current_pick + picks_until
        for pick_a, pick_b in turn_pairs(my_picks):
            if pick_a != next_pick or pick_a < current_pick:
                continue
            for rec_a, rec_b in recommend_pair(
                pool, roster, league_shape, pick_a, pick_b, recent, limit=3
            ):
                turn_pairs_out.append(
                    TurnPairOut(
                        pick_a=pick_a,
                        pick_b=pick_b,
                        recommendation_a=_rec_out(rec_a),
                        recommendation_b=_rec_out(rec_b),
                    )
                )
            break

    data = RecommendationsData(
        current_overall_pick=current_pick,
        picks_until_next=picks_until,
        shortlist=shortlist,
        tier_alarms=tier_alarms_out,
        bye_collisions=bye_collisions_out,
        positional_runs=positional_runs_out,
        advisories=advisories,
        turn_pairs=turn_pairs_out,
    )
    return await _envelope(session, data)


@router.get("/slot-plan", response_model=Envelope[SlotPlanData])
async def get_slot_plan(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[SlotPlanData]:
    """6.4 -- the pre-built slot-1 plan (`board_heuristics._draft_slot_1_plan`),
    recomputed against the live draft: each named target is tagged sniped (drafted by
    another team) / drafted_by_me / still_available rather than rendered as static
    text. `applicable` is false whenever the resolved league shape's `slot != 1` -- the
    frontend must gate rendering on it (the plan's pick numbers and back-to-back
    reasoning are only valid at slot 1 in a 12-team snake), but the data itself is
    still returned so a UI that wants to explain why can.
    """
    response.headers["Cache-Control"] = CACHE_CONTROL

    league_shape, _conflicts, _my_picks, _current, _picks_until = await _league_context(session)

    heuristic = await session.get(BoardHeuristic, "_draft_slot_1_plan")
    payload = json.loads(heuristic.payload) if heuristic is not None and heuristic.payload else {}
    pick_numbers = list(payload.get("pick_numbers") or [])
    structural_note = payload.get("structural_note")
    parsed_entries = parse_slot_plan(payload)

    picks = await draft_state.list_picks(session)
    pick_by_name = {p.player_name: p for p in picks}
    # "Recompute the remainder against the live pool" (task 6.4) means the actual
    # undrafted, draftable pool -- NOT just "no pick recorded". `undrafted_pool` also
    # excludes `out_for_season=True`, so a plan target who's since been ruled out for
    # the year reads as unavailable here too, exactly like it would on the real board.
    pool_names = {c.name for c in await draft_state.undrafted_pool(session)}

    entries_out: list[SlotPlanEntryOut] = []
    planned_picks: set[int] = set()
    for entry in parsed_entries:
        planned_picks.update(entry.picks)
        targets_out = []
        for target in entry.targets:
            pick = pick_by_name.get(target.name)
            sniped = pick is not None and not pick.is_my_pick
            drafted_by_me = pick is not None and pick.is_my_pick
            targets_out.append(
                SlotPlanTargetOut(
                    name=target.name,
                    group=target.group,
                    sniped=sniped,
                    drafted_by_me=drafted_by_me,
                    drafted_by_team=pick.drafted_by_team if sniped else None,
                    still_available=pick is None and target.name in pool_names,
                )
            )
        entries_out.append(
            SlotPlanEntryOut(
                picks=list(entry.picks),
                label=entry.label,
                confidence=entry.confidence,
                rule=entry.rule,
                avoid=list(entry.avoid),
                targets=targets_out,
            )
        )

    data = SlotPlanData(
        applicable=league_shape.slot == 1,
        user_draft_slot=league_shape.slot,
        structural_note=structural_note,
        pick_numbers=pick_numbers,
        entries=entries_out,
        unplanned_pick_numbers=[p for p in pick_numbers if p not in planned_picks],
    )
    return await _envelope(session, data)


def _board_match_out(m: draft_matches.BoardMatch) -> BoardMatchOut:
    return BoardMatchOut(
        board_player_name=m.board_player_name,
        espn_player_id=m.espn_player_id,
        match_method=m.match_method,
        match_confidence=m.match_confidence,
        candidates=[
            EspnMatchCandidateOut(
                espn_player_id=c.espn_player_id,
                full_name=c.full_name,
                position=c.position,
                nfl_team=c.nfl_team,
                is_dst=c.is_dst,
            )
            for c in m.candidates
        ],
    )


@router.get("/matches", response_model=Envelope[MatchesData])
async def get_matches(
    response: Response, session: AsyncSession = Depends(get_session)
) -> Envelope[MatchesData]:
    """4.5 -- every board entry's match state, with candidate ESPN players for anything
    below the 0.9 confidence gate (`MatchesData.below_threshold_count`). On the real
    committed board this is 0 -- see `services/draft_matches.py` for why that keeps the
    ESPN universe fetch off this read path entirely in the common case."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    report = await draft_matches.list_matches(session)
    data = MatchesData(
        matches=[_board_match_out(m) for m in report.matches],
        method_counts=report.method_counts,
        below_threshold_count=report.below_threshold_count,
    )
    return await _envelope(session, data)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@router.post("/picks", response_model=DraftPickOut, status_code=201)
async def create_pick(
    body: RecordPickIn, session: AsyncSession = Depends(get_session)
) -> DraftPickOut:
    if body.player_name is None and body.board_player_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_player",
                "message": "player_name or board_player_id is required",
            },
        )
    try:
        pick = await draft_state.record_pick(
            session,
            player_name=body.player_name,
            board_player_id=body.board_player_id,
            is_my_pick=body.is_my_pick,
            drafted_by_team=body.drafted_by_team,
            overall_pick=body.overall_pick,
            source="manual",
        )
    except DraftPickConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "pick_conflict", "message": str(exc)},
        ) from exc
    return _pick_out(pick)


@router.delete("/picks/last", response_model=UndoResultData)
async def delete_last_pick(session: AsyncSession = Depends(get_session)) -> UndoResultData:
    undone = await draft_state.undo_last_pick(session)
    return UndoResultData(undone=_pick_out(undone) if undone is not None else None)


@router.put("/current-pick", response_model=CurrentPickData)
async def put_current_pick(
    body: CurrentPickIn, session: AsyncSession = Depends(get_session)
) -> CurrentPickData:
    try:
        value = await draft_state.set_current_overall_pick(session, body.overall_pick)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_pick", "message": str(exc)}
        ) from exc

    await session.commit()
    fingerprints = await differ.draft_fingerprints(session)
    differ.diff_and_publish(fingerprints)

    league_shape, _conflicts, my_picks, _current, picks_until = await _league_context(session)
    return CurrentPickData(
        current_overall_pick=value,
        current_round=round_for_pick(value, league_shape.teams),
        picks_until_next=picks_until,
    )


@router.post("/matches/{name}", response_model=BoardMatchOut)
async def override_match(
    name: str, body: MatchOverrideIn, session: AsyncSession = Depends(get_session)
) -> BoardMatchOut:
    """4.5 -- write (or update) a `board_id_overrides` row for board player `name` and
    apply it to the live `BoardPlayer` row immediately (`match_method="override"`,
    `match_confidence=1.0`). `espn_player_id` omitted/`null` records "explicitly no
    ESPN match" -- still a resolved state, per `MatchOverrideIn`'s docstring. Survives
    every subsequent `run_import` re-run (`board_id_overrides` always reapplies)."""
    board_player = await draft_matches.set_override(session, name, body.espn_player_id)
    if board_player is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "board_player_not_found",
                "message": f"No board player named {name!r}",
            },
        )
    return BoardMatchOut(
        board_player_name=board_player.name,
        espn_player_id=board_player.espn_player_id,
        match_method=board_player.match_method,
        match_confidence=board_player.match_confidence,
        candidates=[],
    )
