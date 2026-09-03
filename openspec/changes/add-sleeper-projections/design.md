# Design — add-sleeper-projections

## D1. Why the matcher has three tiers

The obvious design is "Sleeper's player dump carries `espn_id`, join on that." Measured
against this install's 194 rostered players, that reaches **61 of them (32%)**. Sleeper's
`espn_id` is missing for many recently-drafted players — Travis Etienne Jr., Kyle Pitts
Sr. and Tank Dell all lack one.

Measured coverage of the shipped matcher:

| Tier | Rule | Rostered players |
| --- | --- | --- |
| 1 | our ESPN id → dump's `espn_id` | 61 (32%) |
| 2 | `normalize_name(name)` + NFL team | 118 (61%) |
| 3 | D/ST by team abbreviation | 15 (8%) |
| | | **194 (100%)** |

Tier 2 does most of the work. A future reader will assume the opposite, so it is stated
here and in the module docstring.

`normalize_name` is `services/draft_board.normalize_name`, reused rather than
reimplemented — it already folds accents, drops generational suffixes and handles the
apostrophe/hyphen asymmetry.

## D2. Two ways tier 2 could attach the wrong player, both closed

- **Ambiguity.** Two players sharing a normalized name on one NFL team. A full week's
  feed contains zero such collisions today, but the key is dropped rather than resolved
  when it happens: a stranger's projection rendered against a real player is invisible
  once it is a number on screen. Same rule as unmapped injury codes — the wrong answer is
  worse than none.
- **Teamlessness.** 6,617 of ~9,400 feed rows have `team: null` (free agents, practice
  squad). Our own players carry `nfl_team = "FA"`. Letting those two notions of "no team"
  meet would reduce tier 2 to a name-only match, so teamless rows are never indexed and
  an `FA` player never consults tier 2.

## D3. Scope encoding

`week = 0` means season-long totals; 1–18 are scoring periods. A nullable `week` would
have said the same thing, but NULL is not usable in a composite primary key on SQLite.

The two scopes are not interchangeable and the surfaces need different ones: the roster
shows a weekly number (21.57) and `delta_vs_worst_starter` compares season totals
(364.86). Handing one where the other is expected is a silent order-of-magnitude error,
which is why the sentinel is documented in three places.

## D4. Why both projections are shown, never blended

A single merged number would destroy the only thing this data adds. The platform saying
16.2 and Rotowire saying 21.4 for the same quarterback IS the output — it is where a
start/sit decision lives. So `ProjectionCompare` renders the second number quietly and
gives colour only to a divergence of ≥1.5 points; agreement is the common case and
colouring it would drown the rows that matter.

## D5. Undocumented upstream

`docs.sleeper.com` covers leagues, rosters and users. Neither endpoint used here is in
it. That is the same risk class as the ESPN endpoints this app already depends on and is
handled the same way: fail soft, log, keep the last good rows.

One failure mode is escalated rather than swallowed — matching **zero** players when
players exist returns an error onto the `refresh_runs` row. An empty column otherwise
looks identical to "no data this week", and a changed feed shape or a wrong season would
hide behind it indefinitely.
