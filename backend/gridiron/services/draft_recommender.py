"""Pure draft-pick recommendation engine.

No DB session, no HTTP, no `datetime.now()`, no imports from `models/` or `db.py`. Every
time-varying input (current pick, picks until the user's next turn, recent picks, the
user's roster so far) is a parameter -- callers (an API route, a poller, a test) own all
I/O and pass in plain data. The only sibling import is `draft_pick_math`, itself pure.

Score = weighted sum of five components (`value`, `tier_urgency`, `need`, `risk`,
`flags`). The nine `strategy_rules.json` heuristics split two ways:
  - `draft_the_tier`, `flex_pressure`, `injury_discount` feed the weighted score and are
    cited in `fired_rule_ids` when they actually influenced it.
  - `no_kicker`, `qb_wait`, `dst_last` are categorical FILTERS on pool membership, never
    score terms (2.8) -- a QB/DST recommendation still cites the filter that admitted it.
  - `elite_te_window`, `handcuff_own_studs`, `bye_stacking` are advisories, surfaced by
    their own functions rather than folded into any candidate's score.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Sequence

from backend.gridiron.services.draft_pick_math import round_for_pick

# ---------------------------------------------------------------------------
# Public dataclasses (2.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Weights:
    value: float = 1.0
    tier_urgency: float = 1.6  # deliberately the largest -- see 2.4
    need: float = 1.0
    risk: float = 0.8
    flags: float = 0.5


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True)
class Candidate:  # the plain-data view of a board player the engine consumes
    name: str
    position: str
    nfl_team: str | None
    bye: int | None
    adp_rank: int | None
    overall_tier: int | None
    positional_tier: int | None
    risk_score: int | None
    unpriced_risk: bool
    flags: tuple[str, ...]
    off_board: bool = False


@dataclass(frozen=True)
class LeagueShape:
    teams: int
    starters: dict[str, int]  # {"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":2,"DST":1,"K":0}
    flex_eligible: tuple[str, ...]  # ("RB","WR","TE")
    rounds: int
    slot: int


@dataclass(frozen=True)
class Recommendation:
    candidate: Candidate
    score: float
    components: dict[str, float]  # keys: value, tier_urgency, need, risk, flags -- WEIGHTED
    reason: str
    fired_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class TierAlarm:
    position: str
    tier: int
    remaining: int
    picks_until_next: int


@dataclass(frozen=True)
class ByeCollision:
    bye: int
    count: int
    players: tuple[str, ...]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# 2.5 -- flex slots split proportionally across the flex-eligible positions.
FLEX_SHARE = {"RB": 0.45, "WR": 0.45, "TE": 0.10}

_TIER_URGENCY_MAX = 10.0
_VALUE_MIN, _VALUE_MAX = -2.0, 3.0
_ELITE_TE_NAMES = ("Trey McBride", "Brock Bowers")  # named verbatim in elite_te_window's rule text
_ELITE_TE_PICK_THRESHOLD = 30
_QB_WAIT_PICK_THRESHOLD = 50
_QB_WAIT_FALL_THRESHOLD = 8
_FLAG_VALUES = {"TARGET": 1.0, "FADE": -1.0, "NEUTRAL": 0.0, "SLEEPER": 0.0}

# 6.1 -- positional run detection. A "run" at a position is >= 4 of the trailing 8 picks
# (`recent_picks`, ordered most-recent-first -- the same convention `draft_state.recent_picks`
# already returns) landing at that position. Purely a function of the trailing window, so
# it clears on its own as soon as a new pick pushes the count below 4 -- no separate
# "clear" state to track.
_RUN_WINDOW = 8
_RUN_THRESHOLD = 4
_RUN_URGENCY_MULTIPLIER = 1.5


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _tier_counts(pool: Sequence[Candidate]) -> dict[tuple[str, int], int]:
    """Remaining players per (position, positional_tier) among live (not off-board)
    candidates with a known tier."""
    counts: dict[tuple[str, int], int] = {}
    for c in pool:
        if c.off_board or c.positional_tier is None:
            continue
        key = (c.position, c.positional_tier)
        counts[key] = counts.get(key, 0) + 1
    return counts


def replacement_rank(position: str, league: LeagueShape) -> int:
    """Implements `flex_pressure`'s VORP note: replacement rank = dedicated starters at
    `position`, plus that position's proportional share of the league's FLEX slots
    (`FLEX_SHARE`), times team count. In this league (12 teams, 2 RB/2 WR/1 TE/2 FLEX)
    that lands RB and WR at rank 35 -- materially above the naive "starters only" rank of
    24 -- because 2 FLEX slots draw heavily on RB/WR depth."""
    starters_at_pos = league.starters.get(position, 0)
    flex_starters = league.starters.get("FLEX", 0)
    share = FLEX_SHARE.get(position, 0.0)
    return round(league.teams * (starters_at_pos + flex_starters * share))


# ---------------------------------------------------------------------------
# 2.3 value component
# ---------------------------------------------------------------------------


def _value_component(candidate: Candidate, current_pick: int, teams: int) -> float:
    """Rounds of *surplus*: `clamp((current_pick - adp_rank) / teams, -2.0, 3.0)`.

    A candidate is a bargain when he is **still on the board past the pick consensus
    said he'd go** -- `adp_rank < current_pick`. He is a reach when you'd be taking him
    rounds before his price -- `adp_rank > current_pick`, which goes negative.

    This sign is the inverse of the original implementation, which read
    `(adp_rank - current_pick)`. That rewarded candidates for being ranked *later*, and
    because the clamp saturates at +3.0 for anyone `>= 3 * teams` ranks below the
    current pick, in early rounds it pinned essentially the whole board to the maximum
    at once: at pick 1 the top five all scored an identical 22.40 and the shortlist
    ordering fell through to pool order, recommending a WR ranked 74th over the board's
    consensus 1.01. It also contradicted `_passes_qb_wait`, which already used
    `current_pick - adp_rank >= 8` for "has fallen past his ADP"; the module is now
    sign-consistent on "falling."

    NULL `adp_rank` contributes exactly 0.0.
    """
    if candidate.adp_rank is None:
        return 0.0
    return _clamp((current_pick - candidate.adp_rank) / teams, _VALUE_MIN, _VALUE_MAX)


# ---------------------------------------------------------------------------
# 2.4 tier urgency + tier-break alarm + draft_the_tier citation
# ---------------------------------------------------------------------------


def positional_runs(recent_picks: Sequence[Candidate]) -> dict[str, int]:
    """6.1 -- positions currently "running": >= `_RUN_THRESHOLD` (4) of the trailing
    `_RUN_WINDOW` (8) picks landed at that position. `recent_picks` is read
    most-recent-first (matching `draft_state.recent_picks`' `overall_pick.desc()`
    ordering), so the window is simply its first 8 entries -- callers that pass fewer
    than 8 just get a smaller, still-correct window (a run can't be detected on data
    that doesn't exist yet). Pure and stateless: called fresh on every `recommend()`
    invocation, so the flag clears on its own the moment a later pick's window no longer
    has 4 of that position -- there is no separate "clear" step. Positions below the
    threshold are omitted entirely (an empty dict, not zeros), so `pos in positional_runs(...)`
    is the fire condition."""
    window = list(recent_picks)[:_RUN_WINDOW]
    counts: dict[str, int] = {}
    for c in window:
        counts[c.position] = counts.get(c.position, 0) + 1
    return {pos: n for pos, n in counts.items() if n >= _RUN_THRESHOLD}


def _tier_urgency_component(
    candidate: Candidate,
    tier_counts: dict[tuple[str, int], int],
    picks_until_next: int,
    run_boost: bool = False,
) -> float:
    """Urgency = picks_until_next / remaining_in_tier, capped at `_TIER_URGENCY_MAX`: it
    rises as fewer players remain in the candidate's positional tier (more likely to
    break before you pick again) and as picks_until_next rises (more opposing picks that
    could break it). On the clock (`picks_until_next == 0`) there is zero risk of the
    tier surviving PAST this decision -- it's now-or-never -- so that case bypasses the
    division entirely and returns the maximum rather than 0/n.

    `run_boost` (6.1) scales the result up by `_RUN_URGENCY_MULTIPLIER` when the
    candidate's position is currently running (`positional_runs`) -- a live run at a
    position eats its remaining tiers faster than the base picks-until-next/remaining
    ratio assumes, so the same tier should read as more urgent. Still capped at
    `_TIER_URGENCY_MAX`, same as the unboosted case."""
    if candidate.positional_tier is None:
        return 0.0
    remaining = tier_counts.get((candidate.position, candidate.positional_tier), 0)
    if remaining <= 0:
        return _TIER_URGENCY_MAX
    if picks_until_next == 0:
        # On the clock. Returning a flat maximum here (the original behavior) made the
        # highest-weighted term a CONSTANT at exactly the moment recommendations are
        # requested -- every candidate scored the same 10.0, so the term contributed
        # nothing to the ranking it is supposed to dominate. Scale by tier scarcity
        # instead: the last player in his tier is now-or-never (max), one of eight is
        # not. Same ceiling, but it discriminates.
        urgency = _TIER_URGENCY_MAX / remaining
    else:
        urgency = picks_until_next / remaining
    if run_boost:
        urgency *= _RUN_URGENCY_MULTIPLIER
    return min(urgency, _TIER_URGENCY_MAX)


def _draft_the_tier_fires(
    candidate: Candidate, tier_counts: dict[tuple[str, int], int], picks_until_next: int
) -> bool:
    """Citation condition for `draft_the_tier`, independent of `tier_break_alarms`'
    >8-picks-out warning threshold (that's a separate categorical alert). Fires when the
    candidate's tier will plausibly NOT survive to the user's next turn: remaining
    players in the tier <= picks_until_next. On the clock (`picks_until_next == 0`) this
    reduces to `remaining <= 1` -- literally "the LAST player in a breaking tier," the
    rule's own wording.
    """
    if candidate.positional_tier is None:
        return False
    remaining = tier_counts.get((candidate.position, candidate.positional_tier), 0)
    if remaining <= 0:
        return False
    return remaining <= max(picks_until_next, 1)


def tier_break_alarms(pool: Sequence[Candidate], picks_until_next: int) -> list[TierAlarm]:
    """Categorical alert (2.4): fires per (position, tier) with <=2 players remaining AND
    `picks_until_next > 8`. Clears when the tier empties (nothing left to warn about) or
    the user's turn arrives (`picks_until_next == 0`, not > 8)."""
    if picks_until_next <= 8:
        return []
    counts = _tier_counts(pool)
    alarms = [
        TierAlarm(position=pos, tier=tier, remaining=count, picks_until_next=picks_until_next)
        for (pos, tier), count in counts.items()
        if 1 <= count <= 2
    ]
    return sorted(alarms, key=lambda a: (a.position, a.tier))


# ---------------------------------------------------------------------------
# 2.5 roster need + replacement level (flex_pressure)
# ---------------------------------------------------------------------------


def _need_component(
    candidate: Candidate, my_roster: Sequence[Candidate], league: LeagueShape
) -> float:
    """Need = unfilled dedicated starter slots at `candidate.position`, plus (if the
    position is flex-eligible) its `FLEX_SHARE` of whatever FLEX capacity the roster
    hasn't already consumed via flex-eligible overflow. Both terms fall toward 0 as the
    roster fills -- dedicated need directly, flex need because filled-beyond-starters
    flex-eligible players are counted as having already consumed FLEX capacity.

    Scope note: this computes need AT `candidate.position` only. It does not redirect a
    now-filled position's leftover "remainder" into raising OTHER positions' need (e.g.
    filling both RB slots doesn't bump WR's need) -- each candidate's need is evaluated
    independently of every other position's fill state, beyond the shared FLEX pool.
    """
    pos = candidate.position
    starters_at_pos = league.starters.get(pos, 0)
    filled_at_pos = sum(1 for c in my_roster if c.position == pos)
    dedicated_need = max(starters_at_pos - filled_at_pos, 0)

    flex_need = 0.0
    if pos in league.flex_eligible:
        flex_total = league.starters.get("FLEX", 0)
        flex_already_consumed = 0.0
        for p in league.flex_eligible:
            p_starters = league.starters.get(p, 0)
            p_filled = sum(1 for c in my_roster if c.position == p)
            flex_already_consumed += max(p_filled - p_starters, 0)
        flex_remaining = max(flex_total - flex_already_consumed, 0.0)
        flex_need = flex_remaining * FLEX_SHARE.get(pos, 0.0)

    return dedicated_need + flex_need


# ---------------------------------------------------------------------------
# 2.6 risk component (injury_discount) -- gated on unpriced_risk ONLY
# ---------------------------------------------------------------------------


def _risk_component(candidate: Candidate) -> float:
    """`injury_discount`'s rule text defines the trigger as `adp_delta` (`expert_rank -
    adp_rank`) failing to compensate for elevated risk. We can't compute that:
    `expert_rank` doesn't exist anywhere in the board export, and the two substitutes we
    tried both fail on the rule's own canonical cases (Jeremiyah Love, Alec Pierce) --
    `take_in_round - adp_round` isn't a reliable stand-in, and the `FADE` flag is absent
    on both despite their note prose reading "Let someone else pay" / "Hard fade" (see
    task 1.7b: the export drops FADE for high-risk players). `unpriced_risk` is the
    curated, hand-maintained gate that exists specifically to route around this (see
    `UNPRICED_RISK_REVIEW.md`), so it is the ONLY signal used here."""
    if candidate.risk_score is not None and candidate.risk_score >= 4 and candidate.unpriced_risk:
        return -float(candidate.risk_score)
    return 0.0


# ---------------------------------------------------------------------------
# 2.7 flag component
# ---------------------------------------------------------------------------


def _flags_component(candidate: Candidate) -> float:
    return sum(_FLAG_VALUES.get(f, 0.0) for f in set(candidate.flags))


# ---------------------------------------------------------------------------
# 2.8 categorical filters (never score terms)
# ---------------------------------------------------------------------------


def _passes_no_kicker(candidate: Candidate) -> bool:
    """`no_kicker`: never recommend a K, ever. The freed bench slot is surfaced
    separately by `no_kicker_advisory`, not folded into any score."""
    return candidate.position != "K"


def _passes_qb_wait(candidate: Candidate, current_pick: int) -> bool:
    """`qb_wait`: no QB before ~pick 50 unless a top-tier QB (positional_tier == 1) has
    fallen >= 8 picks past his own ADP rank."""
    if candidate.position != "QB":
        return True
    if current_pick >= _QB_WAIT_PICK_THRESHOLD:
        return True
    if (
        candidate.positional_tier == 1
        and candidate.adp_rank is not None
        and current_pick - candidate.adp_rank >= _QB_WAIT_FALL_THRESHOLD
    ):
        return True
    return False


def _passes_dst_last(candidate: Candidate, current_pick: int, league: LeagueShape) -> bool:
    """`dst_last`: no DST until the final two rounds. (The "exactly one" half of the rule
    is enforced later, across the whole shortlist, in `recommend`.)"""
    if candidate.position != "DST":
        return True
    return round_for_pick(current_pick, league.teams) >= league.rounds - 1


def no_kicker_advisory(league: LeagueShape) -> str | None:
    """`no_kicker`'s freed-bench-slot suggestion. Only applies when this league truly
    carries zero kicker starters (as this one does) -- otherwise there's no freed slot."""
    if league.starters.get("K", 0) > 0:
        return None
    return (
        "This league starts no kicker -- never draft one. Use the freed bench slot for a "
        "handcuff on one of your own at-risk RBs, or a second DST to lock a Week 1 matchup."
    )


def elite_te_window_advisories(pool: Sequence[Candidate], current_pick: int) -> list[str]:
    """`elite_te_window`, implemented verbatim from its rule text: McBride/Bowers by name,
    pick 30 by name. No expert-rank comparison needed or possible."""
    if current_pick <= _ELITE_TE_PICK_THRESHOLD:
        return []
    return [
        f"{c.name} is a structural edge (elite_te_window): ADP has fallen into Round 4 "
        f"while expert ranks put him inside the top 25 overall. Still on the board after "
        f"pick {_ELITE_TE_PICK_THRESHOLD} -- take him regardless of weighted rank."
        for c in pool
        if not c.off_board and c.name in _ELITE_TE_NAMES
    ]


def handcuff_advisories(my_roster: Sequence[Candidate]) -> list[str]:
    """`handcuff_own_studs`, keyed off `risk_score` ONLY -- NEVER `injury_tags`, which are
    keyword-derived from note prose and demonstrably unreliable for this purpose (e.g.
    Jahmyr Gibbs carries the tag "mcl" because his note mentions his backup Pacheco's MCL
    sprain, not his own injury). No handcuff mapping exists yet (a later phase owns
    player-to-backup resolution), so this only names the at-risk RB."""
    return [
        f"{c.name} carries elevated risk (risk_score={c.risk_score}) -- consider drafting "
        f"his handcuff late if you can identify one (no handcuff mapping available yet)."
        for c in my_roster
        if c.position == "RB" and c.risk_score is not None and c.risk_score >= 4
    ]


def bye_collisions(my_roster: Sequence[Candidate]) -> list[ByeCollision]:
    """`bye_stacking`: warn when 3+ projected starters share a bye week."""
    groups: dict[int, list[str]] = {}
    for c in my_roster:
        if c.bye is None:
            continue
        groups.setdefault(c.bye, []).append(c.name)
    return [
        ByeCollision(bye=bye, count=len(names), players=tuple(names))
        for bye, names in sorted(groups.items())
        if len(names) >= 3
    ]


# ---------------------------------------------------------------------------
# fired_rule_ids + reason (2.7's non-empty guarantee)
# ---------------------------------------------------------------------------


def _fired_rule_ids(
    candidate: Candidate,
    tier_fires: bool,
    need_component: float,
    risk_component: float,
    league: LeagueShape,
    run_active: bool = False,
) -> tuple[str, ...]:
    fired: list[str] = []
    if tier_fires:
        fired.append("draft_the_tier")
    if candidate.position in league.flex_eligible and need_component > 0:
        fired.append("flex_pressure")
    if risk_component < 0:
        fired.append("injury_discount")
    if candidate.position == "QB":
        fired.append("qb_wait")
    if candidate.position == "DST":
        fired.append("dst_last")
    if run_active:
        # 6.1 -- synthetic id (underscore-prefixed like `_value_calc`/`_positional_cliffs`):
        # not one of strategy_rules.json's 9 named heuristics, but still a real,
        # citable influence on this candidate's tier-urgency term.
        fired.append("_positional_run")
    if not fired:
        # Unconditional fallback -- guarantees non-empty fired_rule_ids for EVERY
        # recommendation (2.7), so the "no rec without a cited rule" rule never has to
        # filter anything out (which would break "return all when pool < 3"). Cites the
        # ADP-vs-replacement value block by its actual board_heuristics.id form.
        fired.append("_value_calc")
    return tuple(fired)


def _build_reason(
    candidate: Candidate,
    fired: tuple[str, ...],
    tier_remaining: int,
    picks_until_next: int,
    recent_tier_hits: int,
    run_count: int = 0,
) -> str:
    parts: list[str] = []
    if "draft_the_tier" in fired:
        parts.append(
            f"Tier {candidate.positional_tier} {candidate.position} is down to "
            f"{tier_remaining} player(s) with {picks_until_next} pick(s) before your next "
            f"turn -- take the tier now."
        )
    if "flex_pressure" in fired:
        parts.append(f"Fills open {candidate.position} need under 2-FLEX pressure.")
    if "injury_discount" in fired:
        parts.append(
            f"risk_score={candidate.risk_score} and the market hasn't priced it in "
            f"(unpriced_risk) -- discounted."
        )
    if "qb_wait" in fired:
        parts.append("Eligible under qb_wait (past pick ~50, or an elite QB fell 8+ picks).")
    if "dst_last" in fired:
        parts.append("Eligible under dst_last (final two rounds).")
    if "_value_calc" in fired:
        parts.append(f"Best available value at ADP rank {candidate.adp_rank}.")
    if recent_tier_hits:
        parts.append(
            f"{recent_tier_hits} peer(s) in this tier taken in the last few picks -- it's "
            f"actively running."
        )
    if "_positional_run" in fired:
        parts.append(
            f"{candidate.position} run in progress: {run_count} of the last "
            f"{_RUN_WINDOW} picks -- tier urgency raised."
        )
    return " ".join(parts)


def _augment_elite_te(rec: Recommendation) -> Recommendation:
    if "elite_te_window" in rec.fired_rule_ids:
        return rec
    return dataclasses.replace(
        rec,
        fired_rule_ids=rec.fired_rule_ids + ("elite_te_window",),
        reason=(
            rec.reason + f" Structural edge (elite_te_window): ADP has fallen into Round 4 while "
            f"expert ranks put {rec.candidate.name} inside the top 25 overall."
        ),
    )


# ---------------------------------------------------------------------------
# 2.9 / main entry point
# ---------------------------------------------------------------------------


def recommend(
    pool: Sequence[Candidate],
    my_roster: Sequence[Candidate],
    league: LeagueShape,
    current_pick: int,
    picks_until_next: int,
    recent_picks: Sequence[Candidate],
    weights: Weights = DEFAULT_WEIGHTS,
    limit: int = 5,
) -> list[Recommendation]:
    """Score and shortlist draftable candidates. `recent_picks` doesn't perturb the
    scored components (kept faithful to the tight 2.3-2.7 formulas) -- it only enriches
    `reason` text when a peer in the candidate's own tier was JUST taken."""
    available = [c for c in pool if not c.off_board]
    tier_counts = _tier_counts(available)
    runs = positional_runs(recent_picks)

    filtered = [
        c
        for c in available
        if _passes_no_kicker(c)
        and _passes_qb_wait(c, current_pick)
        and _passes_dst_last(c, current_pick, league)
    ]

    scored: list[Recommendation] = []
    for c in filtered:
        run_active = c.position in runs
        value = _value_component(c, current_pick, league.teams)
        tier_urgency = _tier_urgency_component(
            c, tier_counts, picks_until_next, run_boost=run_active
        )
        # The multiplier is a no-op whenever `_tier_urgency_component` already returned
        # early at `_TIER_URGENCY_MAX` (on the clock, or an empty tier) -- comparing
        # against the unboosted value is how we tell whether the run ACTUALLY moved
        # this candidate's score, so `_positional_run` is only cited (and the reason
        # text only claims "tier urgency raised") when it's true, never just because a
        # run happens to be live somewhere.
        run_influenced = run_active and tier_urgency > _tier_urgency_component(
            c, tier_counts, picks_until_next, run_boost=False
        )
        need = _need_component(c, my_roster, league)
        risk = _risk_component(c)
        flags = _flags_component(c)

        components = {
            "value": weights.value * value,
            "tier_urgency": weights.tier_urgency * tier_urgency,
            "need": weights.need * need,
            "risk": weights.risk * risk,
            "flags": weights.flags * flags,
        }
        score = sum(components.values())

        tier_remaining = (
            tier_counts.get((c.position, c.positional_tier), 0)
            if c.positional_tier is not None
            else 0
        )
        tier_fires = _draft_the_tier_fires(c, tier_counts, picks_until_next)
        fired = _fired_rule_ids(c, tier_fires, need, risk, league, run_active=run_influenced)
        recent_hits = (
            sum(
                1
                for p in recent_picks
                if p.position == c.position and p.positional_tier == c.positional_tier
            )
            if c.positional_tier is not None
            else 0
        )
        reason = _build_reason(
            c,
            fired,
            tier_remaining,
            picks_until_next,
            recent_hits,
            run_count=runs.get(c.position, 0) if run_influenced else 0,
        )

        scored.append(
            Recommendation(
                candidate=c, score=score, components=components, reason=reason, fired_rule_ids=fired
            )
        )

    scored.sort(key=lambda r: r.score, reverse=True)

    # dst_last: exactly one DST across the whole shortlist, even if several qualify.
    capped: list[Recommendation] = []
    dst_taken = False
    for rec in scored:
        if rec.candidate.position == "DST":
            if dst_taken:
                continue
            dst_taken = True
        capped.append(rec)

    if len(capped) < 3:
        result = capped
    else:
        target_n = max(3, min(limit, 5))
        result = capped[:target_n]

    # elite_te_window: force BOTH named TEs into the shortlist regardless of weighted
    # rank, whenever they're live and pick > 30. Computed as one batch (not one rec at a
    # time) so that forcing McBride in can't turn around and bump Bowers back out again.
    if current_pick > _ELITE_TE_PICK_THRESHOLD:
        forced = [_augment_elite_te(rec) for rec in capped if rec.candidate.name in _ELITE_TE_NAMES]
        if forced:
            forced_names = {r.candidate.name for r in forced}
            keep_from_result = [r for r in result if r.candidate.name not in forced_names]
            budget = max(len(result) - len(forced), 0)
            merged = forced + keep_from_result[:budget]
            merged.sort(key=lambda r: r.score, reverse=True)
            result = merged

    return result


# ---------------------------------------------------------------------------
# 2.10 turn-pair reasoning
# ---------------------------------------------------------------------------


def _pair_is_redundant_single_starter(a: Candidate, b: Candidate, league: LeagueShape) -> bool:
    """True when both picks are the same position AND that position isn't flex-eligible
    with only one (or zero) starter slots -- e.g. two QBs in a 1-QB league. The second
    pick is then dead bench value while a real starter slot elsewhere still needs
    filling; RB/WR/TE doubling up is fine since FLEX always has room for more."""
    if a.position != b.position:
        return False
    if a.position in league.flex_eligible:
        return False
    return league.starters.get(a.position, 0) <= 1


def recommend_pair(
    pool: Sequence[Candidate],
    my_roster: Sequence[Candidate],
    league: LeagueShape,
    pick_a: int,
    pick_b: int,
    recent_picks: Sequence[Candidate],
    weights: Weights = DEFAULT_WEIGHTS,
    limit: int = 5,
) -> list[tuple[Recommendation, Recommendation]]:
    """Recommend combinations for back-to-back picks (`turn_pairs`, e.g. 24/25). Each
    candidate pair is built by recommending pick_a on the clock, then recommending
    pick_b as if pick_a's top candidates were already rostered. Pairs are ranked to
    avoid redundant single-starter positions (see `_pair_is_redundant_single_starter`)
    and prefer distinct positional needs, before combined score."""
    first_picks = recommend(
        pool, my_roster, league, pick_a, 0, recent_picks, weights=weights, limit=limit
    )

    pairs: list[tuple[Recommendation, Recommendation]] = []
    for rec_a in first_picks:
        remaining_pool = [c for c in pool if c.name != rec_a.candidate.name]
        roster_with_a = list(my_roster) + [rec_a.candidate]
        second_picks = recommend(
            remaining_pool,
            roster_with_a,
            league,
            pick_b,
            0,
            recent_picks,
            weights=weights,
            limit=limit,
        )
        for rec_b in second_picks:
            if rec_b.candidate.name == rec_a.candidate.name:
                continue
            pairs.append((rec_a, rec_b))

    def sort_key(pair: tuple[Recommendation, Recommendation]) -> tuple[bool, bool, float]:
        a, b = pair
        redundant = _pair_is_redundant_single_starter(a.candidate, b.candidate, league)
        same_position = a.candidate.position == b.candidate.position
        return (redundant, same_position, -(a.score + b.score))

    pairs.sort(key=sort_key)
    return pairs[:limit]
