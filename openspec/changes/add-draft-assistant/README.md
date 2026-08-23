# add-draft-assistant

Add a live Draft Assistant to GridIron: import the user's hand-built ranking board (149 players + 12 defenses, tiered, with risk scores, TARGET/FADE/SLEEPER flags, theses, sleeper catalysts, attributed analyst takes, and nine machine-readable strategy heuristics), track the draft as it happens, and recommend picks with cited reasoning.

**Source board:** shipped in-repo at `backend/gridiron/draft_board/` — `players.json`, `league_config.json`, `schedule.json`, `strategy_rules.json`, `sources.json`, the source `2026_Draft_Board.xlsx` (whose `DST` tab holds the 12 defenses absent from the JSON), and the board's own `BOARD_SPEC.md`. It lives there rather than under `data/` because `data/` is gitignored. Snapshot date 2026-08-22; ADP from 2,828 12-team half-PPR mock drafts.

**Ordering is the design.** The draft is days away, so phases 1–3 are the shippable core — board, manual mark-drafted, undo, roster panel, tier alarm, recommendations — and they depend on no network call and no ESPN integration. Phases 4–6 are strictly additive. If time runs out mid-change, the user still has a working draft app.

**Scope:** ESPN only for live polling (`mDraftDetail`, armed on request, 2–5 s, cache bypassed). Yahoo is manual entry; its `draftresults` resource is not known to populate before a draft completes.

**Blocking unknown:** whether `mDraftDetail` exposes `inProgress` and a populated `picks` array *while a draft is live*. Task 0.2 captures a mid-mock-draft payload to settle it. A negative finding costs phase 5 and nothing else.

Run `/opsx:apply` to begin implementation.
