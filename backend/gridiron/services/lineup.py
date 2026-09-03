"""Optimal-lineup solver and start/sit advice (add-lineup-optimizer).

The whole feature rests on one thing being true: `_base_slot(roster_slot.slot)` is a
member of `_startable_eligibility(pool_entry.eligible_slots)` for every starter the
platform has already accepted. That was checked against all 300 real starter assignments
in this install before any of this was written, and it is pinned by a test — if the
lineups the platform itself allows are not legal under our eligibility rule, the rule is
wrong and every recommendation built on it is noise.

Three rules keep the advice honest rather than merely optimal:

1. **IR players are excluded structurally**, by roster slot, not by injury designation.
   The platform will not let you start them whatever their status says, and a stale or
   absent `injury_status` on an IR row would otherwise produce "start your IR guy".
2. **Unstartable designations score zero**, and the same zeroing is applied when scoring
   the CURRENT lineup and the optimal one. Score them differently and part of the
   reported gain is an artifact of the rule rather than a real improvement.
3. **A player with no projection is never promoted.** Missing is not zero, and it is not
   the other source's number either — mixing scales was rejected for the same reason the
   two projections are never blended. If they are already starting they stay put: a
   change that cannot be evaluated cannot be justified.
"""

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import schemas
from backend.gridiron.models import League, Player, PlayerPoolEntry, PlayerProjection, RosterSlot
from backend.gridiron.models import Team as TeamRow

# Designations that make a player unstartable regardless of what they project. `Q`, `D`
# and `DTD` are deliberately absent — a questionable player is exactly the judgement call
# the user is here to make, and zeroing them would make it for them.
UNSTARTABLE = frozenset({"O", "IR", "PUP", "SUSP", "NFI"})

# Roster slots that are not starting spots. `BN` players are candidates for promotion;
# `IR` players are not (rule 1).
BENCH_SLOT = "BN"
IR_SLOT = "IR"

# Smallest projected gain worth displacing an incumbent for.
#
# Not cosmetic filtering: a solver told to maximise will happily surface a 0.03-point
# "upgrade", and acting on that is a coin flip dressed as advice — no projection is
# accurate to a tenth of a point.
#
# Applied as an INCUMBENCY PREMIUM inside the objective, not as a filter over the result.
# Filtering afterwards was wrong in a way that only showed up on chained moves: when the
# solver wanted d->WR2 and the displaced b->FLEX1, dropping the immaterial first link left
# b recommended into FLEX1 while still occupying WR2 — a lineup with an empty slot, and a
# `gain` of -5.0 reported next to a move labelled +7.0. Inside the objective a challenger
# simply never displaces an incumbent unless it beats them by this much, so every solution
# the solver returns is already complete, legal and self-consistent.
#
# An unstartable incumbent gets no premium: benching a player who cannot play is right
# even when the replacement projects no better.
MIN_MATERIAL_GAIN = 0.5


@dataclass(frozen=True)
class Candidate:
    """One roster player as the solver sees them."""

    player_id: str
    # Unnumbered base slots this player may start in, e.g. {"RB", "RB/WR", "FLEX", "OP"}.
    eligible: frozenset[str]
    # The raw projection, and the only number ever REPORTED. Zeroed for an unstartable
    # player, and 0.0 for a pinned one with no projection.
    points: float
    # What the solver maximises: `points` plus an incumbency premium for a player already
    # starting. See `MIN_MATERIAL_GAIN`.
    weight: float
    # Distinguishes "projected to score nothing" from "no projection published" — the
    # same distinction the waiver screen's `formatPoints` exists to preserve.
    has_projection: bool
    unstartable: bool
    current_slot: str | None


def _slot_groups(slots: list[str]) -> list[tuple[str, int]]:
    """`["QB","RB1","RB2","FLEX1"]` -> `[("QB",1),("RB",2),("FLEX",1)]`.

    Collapsing the numbered slots into base groups is what makes the search cheap. RB1 and
    RB2 impose an identical eligibility constraint, so treating them as one group with
    capacity 2 shrinks the state space from 2^12 masks to a few hundred capacity vectors —
    ~38k operations for a full roster instead of ~1.2M.
    """
    from backend.gridiron.services.fantasy_service import _base_slot

    counts: dict[str, int] = {}
    for slot in slots:
        base = _base_slot(slot)
        counts[base] = counts.get(base, 0) + 1
    return sorted(counts.items())


def solve(groups: list[tuple[str, int]], candidates: list[Candidate]) -> dict[str, list[str]]:
    """Max-points legal assignment: `{base_slot: [player_id, ...]}`.

    Exact, not greedy. A greedy pass fails the case this feature exists for — the best WR
    belongs in WR1, but whether the *second*-best WR belongs in WR2 or FLEX depends on
    what else can fill FLEX, which greedy cannot see.

    Optimizes `(slots_filled, weight)` lexicographically so a slot is never left empty to
    gain points, which the platform would reject. `weight` carries the incumbency premium;
    the points the caller reports come from `Candidate.points`.
    """
    if not groups:
        return {}

    names = [name for name, _cap in groups]
    caps = [cap for _name, cap in groups]
    # Mixed-radix encoding of "how many of each group are still open".
    radix: list[int] = []
    stride = 1
    for cap in caps:
        radix.append(stride)
        stride *= cap + 1
    total_states = stride

    NEG = (-1, float("-inf"))
    layers: list[list[tuple[int, float]]] = [[NEG] * total_states]
    layers[0][0] = (0, 0.0)

    for cand in candidates:
        cur = layers[-1]
        nxt = list(cur)
        for state, value in enumerate(cur):
            if value == NEG:
                continue
            filled, points = value
            for g, name in enumerate(names):
                if name not in cand.eligible:
                    continue
                used = (state // radix[g]) % (caps[g] + 1)
                if used >= caps[g]:
                    continue
                nstate = state + radix[g]
                better = (filled + 1, points + cand.weight)
                if better > nxt[nstate]:
                    nxt[nstate] = better
        layers.append(nxt)

    best_state = max(range(total_states), key=lambda s: layers[-1][s])

    # Backtrack. Ties resolve to the first eligible group in sorted order, which keeps the
    # result deterministic for the same input — tests depend on that.
    assignment: dict[str, list[str]] = {name: [] for name in names}
    state = best_state
    for i in range(len(candidates) - 1, -1, -1):
        value = layers[i + 1][state]
        if layers[i][state] == value:
            continue  # this player was skipped
        cand = candidates[i]
        for g, name in enumerate(names):
            if name not in cand.eligible:
                continue
            used = (state // radix[g]) % (caps[g] + 1)
            if used == 0:
                continue
            prev = state - radix[g]
            pfilled, ppoints = layers[i][prev]
            if layers[i][prev] != NEG and (pfilled + 1, ppoints + cand.weight) == value:
                assignment[name].append(cand.player_id)
                state = prev
                break
    for name in assignment:
        assignment[name].reverse()
    return assignment


# --------------------------------------------------------------------------------------
# Building candidates from the database
# --------------------------------------------------------------------------------------


def _points_for(
    source: schemas.ProjectionSource,
    roster_row: RosterSlot,
    projection: PlayerProjection | None,
    scoring_type: str | None,
) -> float | None:
    """This source's number for the player, or None when it has none."""
    from backend.gridiron.services.fantasy_service import _resolve_points

    if source == "platform":
        return roster_row.proj_points
    return _resolve_points(projection, scoring_type)


def build_candidates(
    rows: list[tuple[RosterSlot, Player, PlayerPoolEntry | None]],
    projections: dict[str, PlayerProjection],
    *,
    source: schemas.ProjectionSource,
    scoring_type: str | None,
) -> tuple[list[Candidate], list[Player]]:
    """Roster rows -> solver candidates, plus the players this source can't evaluate."""
    from backend.gridiron.services.fantasy_service import _base_slot, _startable_eligibility

    candidates: list[Candidate] = []
    unevaluated: list[Player] = []
    # Current starters first. The DP only overwrites a state on a STRICT improvement, so
    # whoever is considered first wins a tie — ordering incumbents ahead of the bench is
    # what stops an exactly-equal alternative from being reported as a swap.
    rows = sorted(rows, key=lambda r: r[0].slot in (BENCH_SLOT, IR_SLOT))
    for roster_row, player, pool_entry in rows:
        if roster_row.slot == IR_SLOT:
            continue  # rule 1: structural, not status-driven

        eligible = _startable_eligibility(
            json.loads(pool_entry.eligible_slots or "[]") if pool_entry else []
        )
        starting = roster_row.slot != BENCH_SLOT
        if starting:
            # A starter's CURRENT slot is proof of eligibility even when the pool row is
            # missing or stale — the platform already accepted this assignment.
            eligible = eligible | {_base_slot(roster_row.slot)}

        points = _points_for(source, roster_row, projections.get(player.id), scoring_type)
        unstartable = (player.injury_status or "") in UNSTARTABLE
        has_projection = points is not None

        if points is None:
            unevaluated.append(player)
            if not starting:
                continue  # rule 3: never promote on a projection that doesn't exist
            # Already starting: pin them where they are by making their current slot the
            # only thing they're eligible for, and score them 0 so they neither inflate
            # nor deflate the comparison.
            eligible = frozenset({_base_slot(roster_row.slot)})
            points = 0.0

        scored = 0.0 if unstartable else points
        candidates.append(
            Candidate(
                player_id=player.id,
                eligible=frozenset(eligible),
                points=scored,
                # The premium is what makes a change "material". Withheld from an
                # unstartable incumbent, who should always be displaced.
                weight=scored + (MIN_MATERIAL_GAIN if starting and not unstartable else 0.0),
                has_projection=has_projection,
                unstartable=unstartable,
                current_slot=roster_row.slot,
            )
        )
    return candidates, unevaluated


async def _load_roster(
    session: AsyncSession, team_id: str, league_id: str, week: int
) -> list[tuple[RosterSlot, Player, PlayerPoolEntry | None]]:
    rows = (
        await session.execute(
            select(RosterSlot, Player, PlayerPoolEntry)
            .join(Player, RosterSlot.player_id == Player.id)
            .outerjoin(
                PlayerPoolEntry,
                (PlayerPoolEntry.player_id == Player.id) & (PlayerPoolEntry.league_id == league_id),
            )
            .where(RosterSlot.team_id == team_id, RosterSlot.week == week)
        )
    ).all()
    return [(rs, player, pe) for rs, player, pe in rows]


def _starters_from(assignment: dict[str, list[str]]) -> set[str]:
    return {player_id for ids in assignment.values() for player_id in ids}


def starting_entries(
    rows: list[tuple[RosterSlot, Player, PlayerPoolEntry | None]],
) -> list[tuple[str, str]]:
    """Every starting slot as an ordered `(slot_label, current_player_id)` pair.

    A LIST, not a dict keyed by slot label, because slot labels are not unique. The
    internal vocabulary numbers the repeatable positions it knows about (RB1/RB2,
    FLEX1/FLEX2) but leaves QB/TE/K/DST bare — and a real league in this install starts
    TWO kickers, producing `[..., "K", "K", ...]`. Keying by label silently collapsed
    those into one entry and dropped a starter from the recommended lineup, which
    surfaced as a -8.09 gain reported alongside zero moves.
    """
    return [
        (rs.slot, player.id) for rs, player, _pe in rows if rs.slot not in (BENCH_SLOT, IR_SLOT)
    ]


def assign_slots(
    entries: list[tuple[str, str]], assignment: dict[str, list[str]]
) -> list[str | None]:
    """Group-level solver output -> one player per starting slot, positionally aligned
    with `entries`.

    An incumbent keeps the exact slot they already hold, so a two-flex lineup where only
    one flex changes reports one move rather than re-labelling both. Everyone else fills
    what is left, in order.
    """
    from backend.gridiron.services.fantasy_service import _base_slot

    result: list[str | None] = [None] * len(entries)
    for group, optimal_ids in assignment.items():
        positions = [i for i, (slot, _pid) in enumerate(entries) if _base_slot(slot) == group]
        remaining = list(optimal_ids)
        for i in positions:
            incumbent = entries[i][1]
            if incumbent in remaining:
                result[i] = incumbent
                remaining.remove(incumbent)
        for i in positions:
            if result[i] is None and remaining:
                result[i] = remaining.pop(0)
    return result


def _moves(
    entries: list[tuple[str, str]],
    optimal: list[str | None],
    by_id: dict[str, Candidate],
    players: dict[str, Player],
    other_starters: set[str] | None,
) -> list[schemas.LineupMove]:
    """One move per starting slot whose occupant changes.

    Driven positionally by the slot list rather than by pairing two independently-ordered
    lists, which is what removes the two ways the previous version could mislead: naming a
    slot the outgoing player never occupied, and dropping a recommendation when a group
    ended up underfilled.
    """
    moves: list[schemas.LineupMove] = []
    for i, (slot, out_id) in enumerate(entries):
        in_id = optimal[i]
        if in_id is None or in_id == out_id:
            continue
        out_c, in_c = by_id[out_id], by_id[in_id]
        moves.append(
            schemas.LineupMove(
                slot=slot,
                out_player=_player_schema(players[out_id]),
                in_player=_player_schema(players[in_id]),
                out_points=round(out_c.points, 2),
                in_points=round(in_c.points, 2),
                delta=round(in_c.points - out_c.points, 2),
                reason="unstartable" if out_c.unstartable else "higher_projection",
                consensus=(
                    other_starters is not None
                    and in_id in other_starters
                    and out_id not in other_starters
                ),
            )
        )
    moves.sort(key=lambda m: (-m.delta, m.slot))
    return moves


def _player_schema(player: Player) -> schemas.Player:
    from backend.gridiron.services.fantasy_service import _player_schema as build

    return build(player)


async def get_lineup_advice(
    session: AsyncSession,
    team_id: str,
    week: int,
    source: schemas.ProjectionSource = "rotowire",
) -> schemas.LineupAdvice | None:
    """Optimal lineup + the moves to reach it. `None` for an unknown team (the API 404s)."""
    from backend.gridiron.services.fantasy_service import _projections_by_player

    team_row = await session.get(TeamRow, team_id)
    if team_row is None:
        return None
    league_row = await session.get(League, team_row.league_id)
    scoring_type = league_row.scoring_type if league_row else None

    rows = await _load_roster(session, team_id, team_row.league_id, week)
    players = {player.id: player for _rs, player, _pe in rows}
    projections = await _projections_by_player(
        session,
        list(players),
        season=league_row.season if league_row else 0,
        week=week,
    )

    entries = starting_entries(rows)
    groups = _slot_groups([slot for slot, _pid in entries])
    current_ids = {pid for _slot, pid in entries}

    def lineup_for(
        src: schemas.ProjectionSource, other_starters: set[str] | None
    ) -> tuple[list[schemas.LineupMove], set[str], dict[str, Candidate], list[Player], int]:
        cands, unevaluated = build_candidates(
            rows, projections, source=src, scoring_type=scoring_type
        )
        by_id = {c.player_id: c for c in cands}
        optimal = assign_slots(entries, solve(groups, cands))
        moves = _moves(entries, optimal, by_id, players, other_starters)
        final = {pid for pid in optimal if pid is not None}
        evaluated = sum(1 for c in cands if c.has_projection)
        return moves, final, by_id, unevaluated, evaluated

    # The second source is resolved FIRST and only to answer "do they agree?" — its
    # lineup never feeds the recommendation, it only annotates it.
    other_source: schemas.ProjectionSource = "platform" if source == "rotowire" else "rotowire"
    _other_moves, other_final, _other_by_id, _other_unevaluated, other_evaluated = lineup_for(
        other_source, None
    )
    comparison_available = other_evaluated > 0

    moves, final_ids, by_id, unevaluated, evaluated = lineup_for(
        source, other_final if comparison_available else None
    )

    current_points = sum(by_id[pid].points for pid in current_ids if pid in by_id)
    optimal_points = sum(by_id[pid].points for pid in final_ids if pid in by_id)

    return schemas.LineupAdvice(
        team_id=team_id,
        week=week,
        source=source,
        current_points=round(current_points, 2),
        optimal_points=round(optimal_points, 2),
        gain=round(optimal_points - current_points, 2),
        moves=moves,
        sources_agree=bool(comparison_available and other_final == final_ids),
        comparison_available=comparison_available,
        # Counts players this source could actually price. `bool(by_id)` was wrong: a
        # starter with no projection is still added as a pinned candidate, so a source
        # with zero coverage produced a non-empty `by_id`, no moves, and a card reading
        # "Your lineup is optimal." — the exact lie this field exists to prevent.
        advice_available=evaluated > 0,
        unevaluated=[_player_schema(p) for p in unevaluated],
    )
