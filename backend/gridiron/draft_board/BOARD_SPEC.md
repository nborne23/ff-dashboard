# Fantasy Draft Assistant — Build Spec

Handoff package for building a live draft-assistant app. Data snapshot: **2026-08-22**.

---

## 1. What this is

A single-user, live draft companion for one specific league. It is used **during** a snake draft: mark players as taken, see who's left, get a ranked recommendation for the pick that's on the clock, and get warned about tier breaks and roster construction problems.

It is **not** a projections engine and **not** a league-management tool. All ranking inputs are pre-computed and shipped as static JSON.

### Primary user story
> It's my pick. Tell me who to take, why, and what happens if I wait.

---

## 2. League settings (`data/league_config.json`)

| Setting | Value |
|---|---|
| Teams | 12 |
| Draft | Snake |
| Scoring | 0.5 PPR (half point per reception) |
| Starters | 1 QB, 2 RB, 2 WR, 1 TE, 2 FLEX, 1 DST |
| Kicker | **None** |
| Flex eligibility | RB / WR / TE |
| Total starters | 9 |
| User's draft slot | **1.01** |

**User's pick numbers:** 1, 24, 25, 48, 49, 72, 73, 96, 97, 120, 121, 144, 145, 168, 169.

Note that picks 24/25, 48/49, etc. are **back-to-back**. This is the single most important structural fact for the recommendation engine at this draft slot — it should reason about *pairs* of picks, not single picks.

**Unknowns to make configurable:** bench size (not stated by the user; default 6), and the exact non-reception scoring values. Only the 0.5 PPR and the roster shape are confirmed.

---

## 3. Data files

All in `data/`. All are static snapshots — there is no live feed.

### `players.json` — 149 records
Sorted by ADP ascending. Fields:

| Field | Type | Notes |
|---|---|---|
| `name` | string | Primary key. Not guaranteed globally unique across seasons; fine within this dataset. |
| `position` | `QB\|RB\|WR\|TE` | DSTs are **not** in this file (see below) |
| `team` | string | NFL abbreviation |
| `bye` | int | 5–14 |
| `adp` | float\|null | Overall ADP, 12-team half-PPR |
| `adp_rank` | int\|null | Dense rank by ADP |
| `adp_round`, `adp_pick` | int | Precomputed 12-team round/pick |
| `overall_tier` | int\|null | 1–8, from the master board |
| `tier_label` | string | Human-readable tier description |
| `positional_tier` | int\|null | 1–7, within position |
| `positional_tier_label` | string | |
| `risk` | `Low\|Low-Med\|Med\|Med-High\|High` | |
| `risk_score` | 1–5 | Numeric form of `risk` |
| `rookie` | bool | |
| `note` | string | Scouting note; may be long |
| `flags` | array | Any of `TARGET`, `FADE`, `NEUTRAL`, `SLEEPER` |
| `thesis` | string? | Present when flagged TARGET/FADE |
| `take_in_round` | string? | e.g. `"Rd 4"` — the round you actually need to spend |
| `sleeper_category` | string? | e.g. handcuff, post-hype |
| `catalyst` | string? | Why the sleeper could hit |
| `format_fit` | `Redraft\|Best-ball\|Deep`? | |
| `injury_tags` | array | Auto-derived from note text: `ankle`, `groin`, `acl`, `hip`, `toe`, `hamstring`, `mcl`, `pup`, `achilles`, `hernia`, `knee` |
| `out_for_season` | bool | Hard exclude from draftable pool |
| `analyst_takes` | array? | `{source, verified_accuracy, take, detail}` |

Counts: 145 with ADP, 22 targets, 7 fades, 25 sleepers, 11 rookies.

### `schedule.json`
Bye weeks both directions, fantasy playoff weeks (15–17), hardest/easiest playoff schedules, best early-schedule defenses.

### `strategy_rules.json`
Machine-readable heuristics — positional cliffs, recommendation rules, the value calc, and the 1.01 draft plan. **This is the file the recommendation engine should be driven by.** Each heuristic has an `id` so recommendations can cite which rule fired.

### `sources.json`
Which analysts have measured accuracy vs. which are popular-but-unverified, plus data vintage. Use this to weight and attribute.

### DSTs
Not in `players.json`. Twelve defenses live in the source workbook (`2026_Draft_Board.xlsx`, "DST" tab). Either hand-enter them or parse that tab. Top ADP: SEA 81.3, DEN 91.0, HOU 100.5. Best Weeks 1–4 streams: BAL, LAC, DET.

---

## 4. Core features

### 4.1 Draft board (must have)
- All players, filterable by position, sortable by ADP / tier / risk.
- One-tap "mark drafted" — by me or by someone else. Both matter: "drafted by me" builds my roster, "drafted by another team" just removes from pool.
- Undo. **This is essential** — mis-taps happen constantly during a live draft.
- Persist state so a refresh doesn't lose the draft. Note: browser storage APIs are unavailable in some artifact sandboxes; if building as a local app, use a real store, otherwise keep state in memory and add an export/import.

### 4.2 Pick recommender (the point of the app)
Given current pick number and my roster, return a **ranked shortlist of 3–5** with a one-line reason each.

Scoring should combine:
1. **Value vs. ADP** — is he falling past his price?
2. **Tier urgency** — how many players remain in his tier, and will the tier survive until my next pick? Weight this heavily; it's the primary edge in a snake draft.
3. **Roster need** — weighted by starters still unfilled, with FLEX counted as RB/WR demand.
4. **Risk** — penalize `risk_score` 4–5 unless ADP has already discounted it.
5. **Flags** — bonus for `TARGET`, penalty for `FADE`.

Every recommendation must show **why**, citing the heuristic `id` that drove it. Opaque rankings are useless mid-draft.

### 4.3 Tier-break alarm
The highest-value feature after the recommender. When a tier has ≤2 players left and my next pick is >8 picks away, surface a loud warning: *"3 RBs left in Tier 4 — next pick is 11 away."*

### 4.4 Roster construction panel
Live view of filled/unfilled starter slots, bye-week collisions (warn at 3+ starters sharing a bye; Week 11 has six teams off), and positional counts against the 2-FLEX target.

### 4.5 Run detection
Track positions taken in the last 8 picks. If 4+ are one position, flag the run — it changes whether to take the last player in a tier now or wait.

### 4.6 Draft-slot plan view
Read `strategy_rules.json.draft_slot_1_plan` and render the pre-built pick-by-pick plan, checking off steps as they happen and re-planning when a target is sniped.

### 4.7 Player detail
Note, thesis, catalyst, analyst takes, injury tags, bye, schedule context. Attribution should distinguish measured-accuracy sources from unverified ones (per `sources.json`).

---

## 5. Suggested build

Keep it simple and offline-capable — draft night is a bad time for a network dependency.

- **Single-page app**, React or plain TS. No backend required; the data is static JSON.
- **State**: draft state (picks made, by whom), my roster, undo stack.
- **Pure functions** for the scoring engine so it's testable without UI.
- **Mobile-first layout.** This gets used on a phone with a laptop open elsewhere. Big tap targets, minimal scrolling to mark a pick.
- **Performance is trivial** at 149 records — optimize for interaction speed, not data throughput.

### Suggested module split
```
/data           the JSON files (ship as-is)
/engine         scoring, tier analysis, run detection — pure, unit-tested
/state          draft state + undo
/ui             board, recommender, roster panel, player detail
```

### Tests worth writing
- Snake pick-number math for arbitrary slot and team count.
- Tier-survival probability given picks-until-next-turn.
- Roster-need weighting with FLEX correctly counted as RB/WR demand.
- Undo restores exact prior state.

---

## 6. Domain rules that are easy to get wrong

1. **No kicker.** Never recommend one. The freed bench slot should be surfaced as a handcuff or second DST.
2. **FLEX is 2 slots, not 1.** Replacement level for RB/WR is much deeper than a standard league — roughly RB30/WR30, not RB24/WR24. This drives the whole value model.
3. **Tiers beat ranks.** Recommending "highest ranked available" is the naive approach and it's wrong. The correct play is often the last player in a breaking tier.
4. **Injury risk is only a discount if ADP moved.** Several players carry elevated risk with *unchanged or risen* ADP (Jeremiyah Love, Alec Pierce). Those are fades, not values. The engine must compare risk delta against ADP delta, not just look at risk.
5. **Half-PPR, not full.** Some source ranks (Mike Clay) are full PPR. Pure runners nudge up in half-PPR; high-reception players nudge down slightly.
6. **`out_for_season: true` players must be excluded** from the draftable pool but still visible in search, so the user doesn't wonder where they went.

---

## 7. Data freshness and caveats

**This is a snapshot, not a feed.** Everything is accurate as of 2026-08-22.

- ADP moves daily during draft season. If the draft isn't imminent, add a refresh path — Fantasy Football Calculator publishes CSV and JSON endpoints for 12-team half-PPR (referenced in `sources.json`).
- Injury situations are volatile. Several players had unresolved Week 1 status at snapshot time: Jeremiyah Love (high ankle sprain), Emeka Egbuka (toe), Luther Burden III (groin), Sam LaPorta (hip), Malik Nabers (ACL return, not cleared for contact), George Kittle (Achilles), Patrick Mahomes (ACL).
- Bye weeks were verified on 2026-08-22. An earlier version of this dataset had five teams wrong (ARI, CAR, PHI, DEN, LV). Re-verify against the league host before relying on collision warnings.
- `injury_tags` are **derived by keyword match on the note text**, not curated. They will have false positives — e.g. Jahmyr Gibbs is tagged `mcl` because his note mentions *Pacheco's* MCL sprain. Treat as a search aid, not ground truth, or hand-curate before shipping.
- Analyst attributions are quoted from public articles and podcasts. The Fantasy Footballers have no third-party accuracy verification since they stopped submitting to FantasyPros; `sources.json` marks this with `verified_accuracy: false`.
- Scoring values beyond the 0.5 PPR are assumed, not confirmed.

---

## 8. Suggested build order

1. Load data, render a filterable board, mark players drafted, undo. **This alone is usable on draft night.**
2. Roster panel + bye collision warnings.
3. Tier-break alarm.
4. Recommendation engine with reasons.
5. Run detection and the slot-plan view.

Ship 1–3 before draft night if time is short; 4–5 are the polish that makes it genuinely better than a spreadsheet.
