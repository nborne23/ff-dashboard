# Design — add-lineup-optimizer

## D1. The predicate everything rests on

`_base_slot(roster_slot.slot) ∈ _startable_eligibility(pool_entry.eligible_slots)` must
hold for every starter the platform has already accepted. If a lineup ESPN itself allows
is illegal under our rule, the rule is wrong and every recommendation built on it is
noise.

Checked before any solver was written: **300 of 300** real starter assignments across
this install pass, with zero missing pool rows. Pinned by a test.

## D2. Why the solver is exact rather than greedy

Greedy — "best available player into the first slot they fit" — gets the case this
feature exists for wrong. The best WR belongs in WR1; whether the *second*-best WR belongs
in WR2 or FLEX depends on what else can fill FLEX, which greedy cannot see.

Search is a DP over remaining slot capacity. Collapsing numbered slots into base groups is
what makes it cheap: RB1 and RB2 impose an identical eligibility constraint, so a group
with capacity 2 replaces two bitmask positions. A typical lineup is ~7 groups whose
capacities multiply out to a few hundred states — **~38k operations** for a full roster,
against ~1.2M for the naive 2^12 bitmask.

Optimises `(slots_filled, points)` lexicographically: a lineup with a hole is one the
platform rejects, so filling always outranks scoring.

## D3. Three rules that make it honest rather than merely optimal

1. **IR is structural.** IR players are excluded by roster slot, never by injury status. A
   stale or absent `injury_status` on an IR row would otherwise produce "start your IR
   guy", and the platform would reject it anyway. Bench players stay in the pool.
2. **Unstartable scores zero on BOTH sides.** `O`/`IR`/`PUP`/`SUSP`/`NFI` are zeroed when
   scoring the current lineup and the optimal one. Zero them on one side only and part of
   the reported gain is an artifact of the rule. `Q`, `D` and `DTD` keep their projection
   — a questionable player is exactly the judgement the user came here to make.
3. **Missing is not zero, and not the other source's number.** A bench player with no
   projection is never promoted; a starter with none is pinned in place. Falling back to
   the other source for one player would mix scales, which is the same reason the two
   projections are never blended.

## D4. Materiality: immaterial moves are reverted, not hidden

A solver told to maximise will surface a 0.03-point "upgrade". Acting on it is a coin flip
dressed as advice — no projection is accurate to a tenth of a point. Moves below
`MIN_MATERIAL_GAIN` (0.5) are **reverted**, and `gain` is recomputed from the survivors, so
the headline number always equals the sum of the moves actually shown. Hiding them instead
would have left a gain describing changes the user cannot see.

`unstartable` moves ignore the threshold: benching a player who cannot play is right even
when the replacement projects no better.

## D5. Agreement is compared after materiality

Two sources that both say "leave it alone" were initially reported as disagreeing, because
they had picked different immaterial ties. `sources_agree` compares the two
**materialised** lineups, not the raw solver outputs. Same for per-move `consensus`.

The second source is computed only to annotate the recommendation. It is never blended in
— that is the whole reason two projections are worth having.

## D6. Three states that must not collapse

- `advice_available: false` — we could not evaluate (unsynced roster, projections job
  never ran).
- `moves: []` — we evaluated and the lineup is right.
- `moves: [...]` — here is what to change.

Rendering the first as the second is a confident lie the user would act on, which is why
it is a field rather than an inference from an empty list.

## D7. The injury bridge

`players.espn_athlete_id`, populated by the Sleeper refresh from the one dump that carries
`espn_id` and `yahoo_id` on the same record.

Two things worth stating rather than discovering:

- `refresh_injuries` runs every 30 min and `refresh_projections` every 3 h, so on a fresh
  database Yahoo players stay unsupported until the first projections run. A warm-up, not
  a bug.
- D/ST stays unsupported on purpose. A team defense is not an athlete, Sleeper keys
  defenses by team abbreviation, and a bridged value must never resurrect a synthetic
  negative id.
