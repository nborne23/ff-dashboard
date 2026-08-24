## 0. Fixture capture (user-owned, unblocks phases 4–5 only)

> **Deliverable:** real ESPN payloads committed under `tests/fixtures/espn/draft/`. **Risk:** none to phases 1–3, which depend on nothing here — this is deliberately isolated so a negative finding costs only the polling work. **Test:** `mDraftDetail` captured *during a live mock draft* shows `inProgress: true` and a populated `picks` array; if it does not, phase 5 is cut and manual entry stands alone.

- [x] 0.1 (superseded — fetched directly, see design.md OQ1/OQ2) Run `scripts/capture-espn-draft.sh` against the real league (pre-draft) and commit `league_draftdetail.json`, `kona_player_info.json`, `players_wl.json` as fixtures, with the league ID and any personal identifiers scrubbed.
- [~] 0.2 MOVED to `add-draft-live-polling` task 0.1 — a practice draft persists nothing, so only a live real draft can answer this. Re-run the capture **during an ESPN mock draft** and commit `mdraftdetail_inprogress.json`. Record in `design.md` Open Question 1 whether `inProgress` and `picks` populate mid-draft, and the exact field names for pick number, player ID, and drafting team.
- [x] 0.3 From `players_wl.json`, record how D/ST entries are encoded (`defaultPositionId`, id sign/convention, name format) and resolve `design.md` Open Question 2.

## 1. Board data model + import

> **Deliverable:** `sqlite3 data/gridiron.db 'select count(*) from board_players'` returns 161, with tiers and heuristics loaded. **Risk:** low — pure local data, no network. **Test:** re-running the import leaves counts and IDs unchanged. Tasks 1.3–1.5 are parallelizable once 1.1 lands.

- [x] 1.1 `backend/gridiron/models/draft.py`: SQLAlchemy ORM for `BoardPlayer`, `BoardTier`, `BoardHeuristic`, `BoardIdOverride`, `DraftPick`, `DraftSession` per design D2/D1/D4. JSON-valued columns as `TEXT`, dialect-neutral. Add to `models/__init__.py`.
- [x] 1.2 Alembic migration creating all six tables, with indexes on `board_players.normalized_name` and `board_players.espn_player_id`, and unique constraints on `board_players.name` (the conflict target the idempotent upsert in 1.7 needs) and `draft_picks.overall_pick`.
- [x] 1.3 `services/draft_board.py` — `normalize_name()` (NFKD fold, lowercase, strip punctuation, strip `Jr/Sr/II/III/IV`, collapse whitespace) with unit tests covering accented names, suffixes, and the punctuation cases present in the real board.
- [x] 1.4 `services/draft_board.py` — `load_players_json()` parsing all 149 records including the 4 with NULL ADP, normalizing `tier_label`/`positional_tier_label` out into `board_tiers`, and serializing `flags`/`injury_tags`/`analyst_takes` to JSON TEXT. `take_in_round` needs a **range-tolerant** parser: real values include `"Rd 2-3"` and `"Rd 9-10"` alongside `"Rd 4"`, and a plain `int()` raises on them.
- [x] 1.5 `services/draft_board.py` — `load_dst_xlsx()` parsing the workbook's `DST` sheet with stdlib `zipfile` + `xml.etree`, resolving `t="inlineStr"` cells from `<is><t>`, skipping the header and commentary rows, and producing exactly 12 `position='DST'` rows with NULL tiers.
- [x] 1.6 `services/draft_board.py` — `load_strategy_rules()` writing `board_heuristics` keyed by the nine rule `id`s, plus positional cliffs, value calc, and the slot-1 plan.
- [x] 1.7 `python -m gridiron.draft_board import` CLI entrypoint: idempotent upsert of all of the above, emitting a summary report. Test asserts a second run produces identical state.
- [x] 1.7a Seed the curated `unpriced_risk` column (design D6): generate the list of the ~40 players at `risk_score >= 4` with their notes, have the user mark which carry risk the market has **not** priced in, and commit the result as a checked-in seed file the import reads. Pre-seed Jeremiyah Love and Alec Pierce, whose notes state it explicitly ("ADP has actually RISEN"; "far too high"). This replaces `adp_delta`, which is not computable — `expert_rank` is absent from the export and both candidate substitutes fail on exactly these two players.
- [x] 1.7b Import report lists every `risk_score >= 4` player with an empty `flags` array, surfacing the export's missing-`FADE` defect rather than silently under-firing the flag term. Report the list to the user as a source-data fix only they can make.
- [x] 1.8 Acceptance: 161 rows; 22 TARGET, 7 FADE, 25 SLEEPER, 11 rookies match the board's stated counts; import twice, diff the DB, no change.

## 2. Recommendation engine (pure — parallelizable with phase 1)

> **Deliverable:** `services/draft_recommender.py` fully unit-tested with no DB, no HTTP, no clock. **Risk:** the scoring weights are asserted, not fitted — mitigated by exposing every component. **Test:** table-driven cases per scenario in `specs/draft-recommendations/spec.md`. Depends only on the dataclass shape from 1.1, so it runs in parallel with 1.3–1.8. Tasks 2.3–2.7 are parallelizable with each other.

- [x] 2.1 `services/draft_pick_math.py`: snake pick numbers for arbitrary `(teams, slot, rounds)`, `picks_until_next(current_pick)`, and back-to-back turn-pair detection. Test that slot 1 / 12 teams / 15 rounds yields exactly `[1, 24, 25, 48, 49, 72, 73, 96, 97, 120, 121, 144, 145, 168, 169]`, plus a non-12-team, non-slot-1 case.
- [x] 2.2 `services/draft_recommender.py` skeleton: `Weights` dataclass with `DEFAULT_WEIGHTS`, `Recommendation` with `score`/`components`/`reason`/`fired_rule_ids`, and the pure `recommend()` signature from design D6.
- [x] 2.3 Value term: `clamp((adp_rank − current_pick) / teams, −2, 3)`, contributing 0 for NULL `adp_rank`.
- [x] 2.4 Tier-urgency term per design D6, weighted highest, plus the categorical tier-break alarm (≤2 remaining and next pick >8 away) as a separate trigger independent of the score. **Guard `picks_until_next == 0`** — the formula divides by zero and on-the-clock is exactly when recommendations are requested; it evaluates to maximum urgency there.
- [x] 2.5 Roster-need term with FLEX distributed across `flex_eligible` and replacement level computed as `teams × (starters[pos] + flex_share[pos])` per design D7. Test that a 12-team 2-FLEX league lands RB/WR replacement near rank 30, not 24.
- [x] 2.6 Risk term gated on the curated `unpriced_risk` column from 1.7a — **not** on `adp_delta`, which is not computable from this export. Test that a high-risk player whose ADP already priced the risk is *not* penalized while Love and Pierce are.
- [x] 2.7 Flag term (+TARGET, −FADE) and composite assembly, asserting every returned recommendation carries at least one `fired_rule_ids` entry.
- [x] 2.8 Categorical rules as filters, not score terms: `no_kicker`, `qb_wait`, `dst_last`, `elite_te_window` (implemented from the rule text verbatim — it names its own two players and the pick-30 threshold, so no expert-rank comparison is needed), `handcuff_own_studs` (keyed on `risk_score >= 4` only, never `injury_tags`).
- [x] 2.9 `draft_the_tier`: test that the last player in a breaking tier outranks a higher-ranked player from a tier that survives to the next turn.
- [x] 2.10 Turn-pair reasoning: given back-to-back picks, avoid a pair leaving a starter slot unfillable and prefer combinations covering distinct needs.

## 3. Draft state + manual flow + Draft screen — **SHIPPABLE DRAFT-NIGHT MILESTONE**

> **Deliverable:** a Draft screen usable in a real draft with zero ESPN integration: board, filter/sort, one-tap mark-drafted, undo, roster panel, tier alarm, recommendations with reasons. **This is the phase that must land before draft day; everything after is an upgrade.** **Risk:** none external — depends on no network call. **Test:** run a full 15-round mock entirely by hand through the UI; verify undo restores exact prior state and the tier alarm fires. Backend 3.1–3.5 and frontend 3.7–3.12 are parallelizable after 3.1.

- [x] 3.1 `services/draft_state.py`: `record_pick()` (single path for both sources), `undo_last_pick()`, `list_picks()`, `my_roster()`, `undrafted_pool()` excluding `out_for_season`.
- [x] 3.2 `services/draft_state.py`: league-config resolution — ESPN `mSettings` preferred, static `league_config.json` fallback, per-field disagreement list returned for the UI banner. **Reuse `platforms/espn/slot_table.py`** to translate `lineupSlotCounts`' `lineupSlotId` keys; do not write a second lookup table.
- [x] 3.3 `schemas/draft.py`: Pydantic models for board player, pick, session, pool, roster, recommendation (with components and cited rule IDs), and the settings-conflict list, wrapped in the existing `Envelope`.
- [x] 3.4 `api/draft.py`: `GET /api/draft/board`, `GET /api/draft/pool`, `GET /api/draft/state`, `GET /api/draft/recommendations`, `POST /api/draft/picks`, `DELETE /api/draft/picks/last`. Register the router in `main.py`.
- [x] 3.5 `services/differ.py`: add `draft_fingerprints()` over `(max(overall_pick), count(picks), current_overall_pick)` plus session status **when a session exists** — manual-only operation has no `draft_sessions` row until phase 5, so the session term must be optional rather than raising. Publish scope `"draft"`; manual picks publish it too. Test both the with- and without-session paths, and that an unchanged state publishes nothing.
- [x] 3.6 **`frontend/src/api/events.ts`: add `"draft"` to `queryKeyForScope`.** It is a hardcoded whitelist that returns `null` and silently no-ops for unknown scopes — omitting this yields an SSE event that fires, parses, and does nothing, with no error. Add a test asserting `queryKeyForScope("draft") !== null`.
- [x] 3.7 `frontend/src/api/draft.ts`: query hooks for board/pool/state/recommendations and mutations for mark-drafted and undo, with optimistic updates so a tap feels instant.
- [x] 3.8 `screens/Draft/BoardList.tsx`: filterable by position, sortable by ADP/tier/risk, drafted players greyed and struck through rather than removed, large tap targets.
- [x] 3.9 `screens/Draft/MarkDrafted.tsx` + undo control: distinguish a pick by the user from a pick by another team; undo visible without scrolling.
- [x] 3.9a `screens/Draft/CurrentPick.tsx` (design D13): always show current overall pick, round, and picks-until-next-turn, with a control to set the pick number directly. Marking advances it; the ESPN poll overwrites it once armed. Without this, a user who marks only some picks gets tier alarms computed against a wrong `picks_until_next`, silently — and this is on the must-ship path.
- [x] 3.10 `screens/Draft/RosterPanel.tsx`: filled/unfilled starter slots from the league's real roster shape, FLEX as its own slots, no kicker slot, bye-collision warning at 3+ shared byes using platform bye weeks.
- [x] 3.11 `screens/Draft/Recommendations.tsx`: the 3–5 shortlist at the top of the screen with one-line reasons and inspectable cited heuristics; tier-break alarm rendered prominently; turn pairs shown together.
- [x] 3.12 `routes.tsx` `/draft` route + `Sidebar.tsx` nav item, matching existing patterns.
- [~] 3.13 NOT RUN — the user's real draft was conducted in ESPN directly, so the hand-driven mock never happened. Acceptance: complete a hand-driven 15-round mock draft in the UI on a phone-width viewport, marking only *some* picks and correcting the pick number by hand; state survives a backend restart; undo is exact; the tier alarm fires against the corrected pick number, not the pick count.

## 4. ESPN player-ID matching + QA gate

> **Deliverable:** all 161 board entries matched or explicitly resolved, gating live mode. **Risk:** the highest-consequence failure in the change — a silently unmatched top player never greys out and keeps getting recommended. **Test:** the QA report lists zero entries below confidence 0.9 after resolution. Requires fixtures from 0.1/0.3. Tasks 4.2–4.4 are parallelizable.

- [x] 4.1 `platforms/espn/draft.py`: `fetch_player_universe()` against `players_wl` (no cookies, no league ID required), parsed against the 0.1 fixture.
- [x] 4.2 `services/draft_board.py` — layered matcher implementing design D3's precedence table (`override` → `exact` → `team_changed` → `name_only` → `fuzzy` ≥ 0.88 → `unmatched`), recording `match_method` and `match_confidence`. Ambiguous multi-candidate results record `unmatched`, never a guess.
- [x] 4.3 DST matching by NFL team abbreviation against `defaultPositionId == 16`, using the encoding confirmed in 0.3. Name-based methods are not attempted for defenses.
- [x] 4.4 Board-vs-platform bye-week reconciliation: ESPN wins, discrepancies logged at import.
- [x] 4.5 `GET /api/draft/matches` + `POST /api/draft/matches/{name}` writing `board_id_overrides`; overrides applied first on every subsequent import.
- [x] 4.6 `screens/Draft/MatchResolution.tsx`: the resolution list with candidate players; live mode gated behind it while any entry is below 0.9; manual board use unaffected.
- [x] 4.7 Acceptance: run the import against real fixtures, resolve the exception list, re-run the import, confirm every override survived.

## 6. Polish

> **Deliverable:** the features that make this better than a spreadsheet rather than merely equal to one. **Risk:** low; all additive. **Test:** each scenario in `specs/draft-recommendations/spec.md` and `specs/draft-ui/spec.md` has a passing test. Every task here is parallelizable.

- [x] 6.1 Positional run detection: 4+ of the last 8 picks at one position raises the flag and the tier-urgency contribution for that position; clears when the trailing count drops.
- [x] 6.3 `screens/Draft/PlayerDetail.tsx`: note, thesis, take-in-round, sleeper category, catalyst, format fit, bye, tier labels, risk, and analyst takes with `verified_accuracy` visually distinguished; injury tags labelled advisory.
- [x] 6.4 `screens/Draft/SlotPlan.tsx`: render the slot-1 plan only when the user's actual slot is 1; mark sniped targets and recompute the remainder against the live pool.
- [x] 6.5 Degraded-mode behavior per design D12: 5-second draft-query polling while the Draft screen is mounted **and** SSE is disconnected, scoped to this screen only so the app-wide 5-minute fallback is untouched elsewhere.
- [x] 6.6 Settings-conflict banner naming each field where ESPN and the static config disagree, or that could not be read.
- [x] 6.7 Out-for-season players excluded from the pool but findable by search with a clear marker.
- [x] 6.8 README section: how to run the import, arm a draft, and what to do when ESPN breaks mid-draft — including keeping a printed board as the backstop, since the app is the backend.

## 7. Status at archive (2026-08-24)

Shipped: phases 1, 2, 3, 4, 6 (less 6.2). 493 backend tests, 138 frontend tests, lint and builds clean.

Deferred to change `add-draft-live-polling`: all of phase 5 (armed ESPN polling, cache bypass, audit suppression, reconciliation, session control) and 6.2 (off-board tail). Gated on whether `mDraftDetail` populates picks *during* a draft — unresolved, and unresolvable until the next live one.

Not run: 3.13 (hand-driven mock through the UI) and 4.7's live re-import against real fixtures, though override survival was proven against a real double import in `test_match_override_survives_a_real_reimport`.

The Draft screen ships behind `frontend/src/features.ts`'s `DRAFT_ASSISTANT` flag, currently **false** — the feature is complete but hidden between drafts. The backend API and board import stay live regardless.
