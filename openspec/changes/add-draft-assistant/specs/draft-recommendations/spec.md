## ADDED Requirements

### Requirement: Recommendation engine is pure

The recommendation engine SHALL be implemented as pure synchronous functions taking `(pool, my_roster, league, current_pick, picks_until_next, recent_picks, weights)` and returning a ranked list. It SHALL perform no I/O, hold no database session, and read no clock — every time-varying input SHALL be a parameter.

#### Scenario: No side effects

- **WHEN** the engine is called twice with identical arguments
- **THEN** it returns identical results, and it can be exercised in unit tests with no database, no HTTP, and no fixtures beyond plain data structures.

#### Scenario: Buildable before integration

- **WHEN** neither the ESPN poller nor the board matcher exists yet
- **THEN** the engine is still fully implementable and testable against hand-constructed pools.

### Requirement: Ranked shortlist with mandatory reasoning

The system SHALL return a ranked shortlist of 3–5 candidates for the pick on the clock. Every recommendation SHALL carry a one-line reason and the `board_heuristics` `id`s that produced it. A recommendation without a cited rule SHALL NOT be returned.

#### Scenario: Shortlist shape

- **WHEN** recommendations are requested with a non-empty pool
- **THEN** between 3 and 5 candidates are returned in descending score order, each with its composite score, the individual score components, a one-line reason, and at least one heuristic `id`.

#### Scenario: Components exposed

- **WHEN** a recommendation is returned
- **THEN** its value, tier-urgency, need, risk, and flag contributions are individually readable, so the UI can show why rather than a bare number.

#### Scenario: Near-empty pool

- **WHEN** fewer than 3 draftable players remain
- **THEN** all remaining players are returned rather than raising or padding the list.

### Requirement: Composite scoring model

The system SHALL score candidates by a weighted sum of value-versus-ADP, tier urgency, roster need, risk, and board flags. Weights SHALL be defined in one place and SHALL be adjustable without touching scoring logic.

#### Scenario: Value versus ADP

- **WHEN** a player's `adp_rank` is later than the current overall pick
- **THEN** he scores positively on value in proportion to how many rounds he is falling past his price, clamped to a bounded range.

#### Scenario: Players without ADP

- **WHEN** a candidate has a NULL `adp_rank`
- **THEN** his value term contributes zero and he is scored on the remaining terms without error.

#### Scenario: On the clock

- **WHEN** `picks_until_next` is 0, which is precisely when recommendations are requested
- **THEN** tier urgency evaluates to its maximum rather than dividing by zero, because a tier's survival to a later turn is no longer at issue.

#### Scenario: Tier urgency dominates

- **WHEN** weights are applied
- **THEN** tier urgency carries the largest weight, because tier structure rather than raw ranking is the primary edge in a snake draft and "take the highest-ranked player available" is the naive approach the board explicitly rejects.

#### Scenario: Risk only penalized when unpriced

- **WHEN** a candidate has `risk_score` of 4 or 5
- **THEN** a risk penalty applies **only** if his curated `unpriced_risk` flag is true; a player whose ADP already fell far enough to price the risk in receives no penalty, while one whose risk rose with unchanged or rising ADP is penalized. This implements `injury_discount`.

#### Scenario: The risk gate is curated, not computed

- **WHEN** the risk gate is implemented
- **THEN** it reads the curated `unpriced_risk` column and SHALL NOT attempt to compute `adp_delta` from `expert_rank`, which does not exist in the board export, nor substitute `take_in_round − adp_round` or the `FADE` flag, both of which fail on the canonical cases.

#### Scenario: Flags adjust the score

- **WHEN** a candidate carries `TARGET` or `FADE`
- **THEN** the score is adjusted upward or downward respectively; `NEUTRAL` and `SLEEPER` contribute nothing to this term. This term is known to under-fire: the board export omits `FADE` on at least two players whose notes describe them as fades, so it SHALL NOT be the only mechanism guarding against overpaying for risk — `unpriced_risk` is.

### Requirement: Roster need with FLEX counted as real demand

Roster need SHALL be computed from starter slots still unfilled in the user's live draft roster, with FLEX slots distributed across flex-eligible positions. Replacement level SHALL be derived from league settings rather than assumed from a standard single-FLEX league.

#### Scenario: FLEX distributed

- **WHEN** the league has 2 FLEX slots eligible for RB/WR/TE
- **THEN** those slots add to RB, WR, and TE demand by a documented share rather than being treated as a single position or ignored.

#### Scenario: Replacement level reflects FLEX

- **WHEN** replacement level is computed for a 12-team league with 2 RB, 2 WR, 1 TE, and 2 FLEX
- **THEN** RB and WR replacement lands near rank 30 rather than 24, because up to 54 RB/WR/TE start weekly across the league, and RB/WR depth is weighted accordingly. This implements `flex_pressure`.

#### Scenario: Need falls as slots fill

- **WHEN** the user has already drafted enough players at a position to fill its starter slots
- **THEN** need at that position drops toward zero and remaining demand shifts to unfilled positions.

### Requirement: Categorical rules run as filters, not score terms

Rules that state absolutes SHALL be applied as filters, forced inclusions, or alerts — never folded into the weighted sum, which would reduce a prohibition to a preference.

#### Scenario: No kicker, ever

- **WHEN** recommendations are produced
- **THEN** no kicker is ever recommended, and the freed bench slot is surfaced as a handcuff or second-DST suggestion. This implements `no_kicker`.

#### Scenario: QB wait

- **WHEN** the current pick is earlier than approximately pick 50
- **THEN** no QB is recommended unless the top-tier QB has fallen at least 8 picks past his ADP. This implements `qb_wait`.

#### Scenario: DST last

- **WHEN** the draft is not within its final two rounds
- **THEN** no DST is recommended; within the final two rounds exactly one DST is recommended, prioritizing Weeks 1–4 schedule over season-long ranking. This implements `dst_last`.

#### Scenario: Elite TE window

- **WHEN** either of the two elite TEs named in the `elite_te_window` rule text is available after pick 30
- **THEN** he is flagged as a structural edge and surfaced regardless of his weighted position in the shortlist. The rule names its own players and threshold, so it is implemented from the rule text verbatim and requires no expert-rank comparison. This implements `elite_te_window`.

#### Scenario: Handcuff own studs

- **WHEN** a rostered RB has `risk_score` of 4 or higher
- **THEN** his handcuff is surfaced as a late-round suggestion. This rule SHALL key off `risk_score` **only** and SHALL NOT key off `injury_tags`, which are keyword-derived and known to produce false positives. This implements `handcuff_own_studs`.

### Requirement: Tier-break alarm

The system SHALL warn when a tier is about to become unavailable before the user's next turn. This is the highest-value alert in the feature after the shortlist itself.

#### Scenario: Alarm fires

- **WHEN** a tier has 2 or fewer players remaining and the user's next pick is more than 8 picks away
- **THEN** a prominent warning is raised naming the position, the count remaining, and the number of picks until the user's next turn.

#### Scenario: Alarm clears

- **WHEN** the tier empties or the user's turn arrives
- **THEN** the warning clears without requiring a page reload.

#### Scenario: Last player in a breaking tier

- **WHEN** the last player of a tier is available and the next tier begins within the user's next-pick window
- **THEN** he is recommended above a higher-ranked player from a tier that will survive, and the recommendation cites `draft_the_tier`.

### Requirement: Positional run detection

The system SHALL detect positional runs, because a run changes whether to take the last player in a tier now or wait.

#### Scenario: Run flagged

- **WHEN** 4 or more of the last 8 picks are at the same position
- **THEN** a run at that position is flagged and the tier-urgency contribution for that position is raised.

#### Scenario: Run clears

- **WHEN** subsequent picks bring the trailing-8 count below 4
- **THEN** the flag clears.

### Requirement: Bye-week collision warnings

The system SHALL warn about bye-week clustering among projected starters, using platform-sourced bye weeks.

#### Scenario: Collision warning

- **WHEN** 3 or more of the user's projected starters share a bye week
- **THEN** a warning names the week and the affected players, with Week 11 called out specifically as the heaviest bye week with six teams off.

#### Scenario: Bye source

- **WHEN** a bye week is used for a collision warning
- **THEN** the value comes from the platform's player record rather than the static schedule file, whose bye weeks were wrong for five teams in a prior revision.

#### Scenario: Byes do not override value

- **WHEN** a candidate would create a bye collision
- **THEN** the collision is surfaced as a warning and does not by itself remove him from the shortlist.

### Requirement: Turn-pair reasoning at back-to-back picks

The system SHALL reason about pairs of picks rather than single picks when the user holds consecutive selections, which is the defining structural feature of drafting from an end slot.

#### Scenario: Pair recommendation

- **WHEN** the user is on the clock for the first of two back-to-back picks
- **THEN** recommendations account for both selections, avoiding a pair that leaves a starter slot unfillable and preferring combinations that cover distinct positional needs.

### Requirement: Slot plan view

The system SHALL render the pre-built pick-by-pick plan from the board's strategy rules, and SHALL do so only when it actually applies.

#### Scenario: Plan gated on slot

- **WHEN** the user's draft slot is not 1
- **THEN** the pre-built slot-1 plan is not presented as applicable, because its pick numbers and its back-to-back-picks reasoning are valid only at slot 1 in a 12-team snake.

#### Scenario: Plan tracks reality

- **WHEN** the user is at slot 1 and a planned target is taken by another team
- **THEN** that step is marked sniped and the remaining plan is recomputed against the live pool.
