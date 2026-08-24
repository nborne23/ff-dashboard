## Why

GridIron is read-only consumption: it tells the user how teams they already own are doing. The one moment in a fantasy season where a dashboard can change the outcome rather than report it is the draft — and it is exactly the moment GridIron is useless.

The user has already done the expensive half of the work. A hand-built board (`backend/gridiron/draft_board/`) holds 149 ranked players plus 12 defenses with overall and positional tiers, ADP, risk scores, TARGET/FADE/SLEEPER flags, scouting notes, per-player theses, sleeper catalysts, attributed analyst takes, and — critically — a `strategy_rules.json` of machine-readable heuristics with stable `id`s. That board is currently a spreadsheet. During a live draft, a spreadsheet cannot tell you that three players remain in a tier and your next pick is eleven picks away, and it cannot cross off the 40 players already taken.

**The draft is within days.** That constraint drives the entire shape of this change: the board plus manual mark-drafted plus the tier-break alarm must ship as a screen that is genuinely usable on draft night *by itself*, before a single line of live-polling code exists. Everything after that is an upgrade to something that already works.

## What Changes

**Board import (static, re-runnable).** A CLI/admin import reads the JSON board into new `board_players`, `board_tiers`, and `board_heuristics` tables, then matches each of the 161 board entries to an ESPN player ID by normalized name + position + NFL team. Matching is the highest-risk step in the change — the board's primary key is a player *name* — so unmatched and low-confidence matches are surfaced for manual resolution rather than silently dropped, and a persisted override table makes a correction permanent across re-imports.

**A pick log, not an ESPN mirror.** Draft state lives in a `draft_picks` table with a `source` column (`manual` | `espn`) and a monotonic `overall_pick`. Manual taps and polled ESPN picks write the same rows through the same service. This is deliberate: it makes the manual flow the primary, always-available path, makes ESPN polling an accelerator rather than a dependency, and makes undo a single well-defined operation regardless of where a pick came from.

**An armed-only ESPN draft poller.** A new `poll_draft` scheduler job registered without a trigger, started by an explicit `POST /api/draft/arm` and stopped on repeated `inProgress: false` ticks **or** a hard wall-clock ceiling. It polls ESPN's `mDraftDetail` view every 2–5 s. It **bypasses `http_cache` entirely** — the existing `_cached_league_fetch` path would serve six-hour-stale draft state — and does **not** write a `refresh_runs` audit row per tick, which at 2 s over a three-hour draft would be ~5,000 rows. The existing adaptive cadence is untouched; when disarmed, this feature adds zero background work.

**A recommendation engine as pure functions.** `services/draft_recommender.py` takes `(board, picks, my_roster, league_config)` and returns a ranked shortlist with the `strategy_rules.json` heuristic `id`s that fired. No I/O, no ORM, fully unit-testable, and buildable before any platform integration works. It combines value-vs-ADP, tier urgency weighted by picks-until-next-turn, roster need with FLEX counted as RB/WR demand, risk (discounted only when ADP actually moved to compensate), and flag bonuses. Every recommendation shows its reasoning; an opaque ranking is worthless mid-draft.

**A Draft screen** at `/draft`, matching the existing design language, pushing updates over the existing SSE channel via a new `draft` scope.

**League settings are read from ESPN, not assumed.** `league_config.json` says 12-team, half-PPR, 1QB/2RB/2WR/1TE/2FLEX/1DST, no kicker, user at 1.01 — none of which is confirmed. The system reads teams, roster slots, scoring, and draft order from ESPN `mSettings`/`mDraftDetail`, falls back to the static file when ESPN is unreachable, and warns loudly when the two disagree. Pick numbers are computed from `(teams, slot, rounds)`; the pre-built 1.01 plan renders only when the user is actually at slot 1.

**Out of scope, deliberately:** Yahoo live draft polling. Yahoo's `draftresults` resource is not known to populate before a draft completes, and verifying that costs time this change does not have. Yahoo is manual-entry only, with post-draft import noted as a follow-up.

## Capabilities

### New Capabilities

- `draft-board`: Board schema (overall + positional tiers, ADP, risk, flags, theses, sleeper catalysts, analyst takes with accuracy tiers, injury tags, `out_for_season`), the DST tab extraction, the idempotent import, ESPN player-ID matching with confidence scoring, and the manual-override/QA surface for unmatched entries.
- `draft-tracking`: The `draft_picks` log with dual `manual`/`espn` provenance and undo; league-settings resolution with ESPN-vs-static conflict warnings; snake pick-number math for arbitrary slot and team count; the undrafted-player pool; the armed-only ESPN `mDraftDetail` poller with its arm/disarm lifecycle, cache bypass, and audit-row suppression.
- `draft-recommendations`: The pure scoring engine — value vs ADP, tier survival given picks-until-next-turn, roster need with 2-FLEX replacement levels, risk-vs-ADP-delta discounting, flag weighting — plus tier-break alarms, positional-run detection, bye-week collision warnings, and mandatory heuristic-`id` citation on every recommendation.
- `draft-ui`: The `/draft` screen — filterable live board with drafted players struck through, roster-construction panel, tier-break alarm, recommendation shortlist with reasons, player detail with attributed analyst takes, the slot-plan view, and offline/degraded-mode behavior for draft night.

### Modified Capabilities

None. `openspec/specs/` is empty — `scaffold-gridiron` has not been archived, so its `live-updates` and `gridiron-ui` capabilities exist only as change deltas and there is no deployed spec to write a delta against. The new `draft` SSE scope and the `poll_draft` job are additive and are specified inside `draft-tracking`; reconciling them into `live-updates` is an archive-time concern, noted in Impact.

## Impact

**New backend code**: `models/draft.py` (`board_players`, `board_tiers`, `board_heuristics`, `board_id_overrides`, `draft_picks`, `draft_sessions`), one Alembic migration, `services/draft_board.py` (import + matching), `services/draft_state.py` (pick log, roster derivation, undrafted pool), `services/draft_recommender.py` (pure engine), `platforms/espn/draft.py` (uncached `mDraftDetail` + `kona_player_info` fetches), `api/draft.py`, a new `poll_draft` entry in the `scheduler.JOBS` registry, and `schemas/draft.py`.

**Modified backend code**: `scheduler.py` gains a registry entry plus arm/disarm helpers and an audit-suppression path in `run_job`; `services/differ.py` gains a `draft` fingerprint scope.

**Modified frontend code**: `routes.tsx` (new `/draft` route), `components/shell/Sidebar.tsx` (new nav item), and — easy to miss and silently fatal — `api/events.ts`'s `queryKeyForScope`, which is a hardcoded whitelist that returns `null` for unknown scopes. A `draft` scope not added there produces an SSE event that does nothing, with no error.

**New frontend code**: `screens/Draft/` and `api/draft.ts`.

**Repo data**: the board ships tracked under `backend/gridiron/draft_board/` (`data/` is gitignored, so it cannot live there) — five JSON files, the source `.xlsx`, and the board's own `BOARD_SPEC.md`.

**Dependencies**: none new. The `.xlsx` DST tab uses inline strings and is parsed with the stdlib `zipfile` + `xml.etree`; no `openpyxl`.

**Data-quality constraints carried from the board's own spec**: `injury_tags` are keyword-derived from note text and demonstrably wrong (Jahmyr Gibbs is tagged `mcl` because his note mentions *Pacheco's* MCL sprain), so the `handcuff_own_studs` heuristic keys off `risk_score >= 4` only. Bye weeks for collision warnings come from the platform's `Player.bye_week`, not `schedule.json`, whose byes were wrong for five teams in a prior revision; `schedule.json` is used only for the playoff-schedule extras ESPN does not provide. The board covers 161 players against roughly 180 picks in a 12-team draft, so the pool needs an explicitly-labeled off-board tail ordered by ESPN ADP.

**Unverified upstream assumption**: that ESPN's `mDraftDetail` exposes `inProgress` and a populated `picks` array *while a draft is live*, not only after it completes. Confirming this against a captured mock-draft payload is the first task of the polling phase, and the manual pick flow is designed to be fully sufficient if it turns out to be false.

**Archive-time note**: when `scaffold-gridiron` is archived, `live-updates` should absorb the `poll_draft` job and the `draft` SSE scope, and `gridiron-ui` should absorb the `/draft` route.
