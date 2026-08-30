> **Parallelism.** Group 1 is the gate — it fixes the contract both sides code against.
> Once it lands, groups 2 (backend), 3 (frontend data), 4+5 (view + styles), and 6.1
> (`projectedFinal`) run as four independent lanes. Group 4 can build against a fixture
> shaped by group 1 without waiting for group 2's endpoint. Group 7 joins the lanes.

## 1. Contract (gate — do first, everything else forks from here)

- [x] 1.1 Add `home_state` / `away_state` (`GameState | None`) and `home_is_live` / `away_is_live` (`bool`) to `MatchupSlot` in `backend/gridiron/schemas/matchups.py`. Import `GameState` from `schemas/roster_slots.py` — do not redeclare the literal.
- [x] 1.2 Add `GameDayMatchup` and `GameDayData` models to `backend/gridiron/services/fantasy_service.py`, beside `H2HData`. Fields per `specs/fantasy-data-model/spec.md` "Bulk game-day matchups". **No `win_prob` field** (design D7).
- [x] 1.3 Mirror both in `frontend/src/types/api.ts`: extend `MatchupSlot`, add `GameDayMatchup` / `GameDayData`.
- [x] 1.4 Write `frontend/src/screens/GameDay/fixtures.ts` — a six-matchup fixture ported from the prototype's `data-gameday.jsx`, typed as `GameDayData`. Unblocks lane 4 before the endpoint exists; drop the `redzone` field (out of scope). *(Authored from spec/design — `design/data-gameday.jsx` does not exist in this repo or its git history.)*

## 2. Backend — endpoint (lane A)

- [x] 2.1 In `fantasy_service.py`, populate the four new `MatchupSlot` fields in `get_h2h()` by joining `RosterSlot` on `(player_id, week)` — **not** `(team_id, week, slot)` (design D6: Yahoo and ESPN build matchup slots differently, so slot labels are not a cross-platform join key). *(Deviation: joined on `(team_id, week, player_id)`, scoping player identity to the matchup's own home/away team. D6's premise that `(player_id, week)` is uniquely constrained is wrong — `roster_slots`' constraint is `uq_roster_slots_team_week_player`, so a player rostered in two of the user's leagues has a row per team and the unscoped join would pick up the wrong league's state. The slot label is still not the key, which is what D6 was actually rejecting.)*
- [x] 2.2 Do the same in `_pair_matchup_slots()`, which already holds the `RosterSlot` rows and can read `game_state` / `is_live` off them directly.
- [x] 2.3 Implement `fantasy_service.game_day(session, week)`. *(Deviation: `_team_schema` is deliberately NOT called — it costs ~4 queries per team and 3 of its outputs (`spark_last_6`, `accent_color`, `is_live`) are not on `GameDayMatchup`, so reusing it would break 2.4 and the spec's normative "No N+1" scenario. The shared fields are derived here from the same sources it uses.)* Reuse `_team_schema` for the fields `Team` already computes (`record`, `rank`, `current_score`, `current_opp_score`, `current_opponent_name` — all week-scoped, verified); join `League` for `league_name`; take `proj`/`opp_proj`/`is_complete` from `Matchup`; call `_remaining_count` per side. Derive `platform` by splitting the team id's `{platform}:` prefix — **it is not a field on `Team`**.
- [x] 2.4 Verify 2.3 issues a bounded number of queries regardless of team count — batch the matchup, slot, player, and roster-slot loads rather than looping per team.
- [x] 2.5 Register `GET /api/teams/game-day` in `backend/gridiron/api/teams.py` **above** the `/{team_id}` route (line ~67), following the `/day-rings` precedent. Set `CACHE_CONTROL`, resolve week via `_resolve_week`, return via `_envelope`.

## 3. Frontend — data layer (lane B)

- [x] 3.1 Add `useGameDay(week)` to `frontend/src/api/teams.ts` — `queryKey: ["gameday", week]`, `staleTime: STALE_TIME_MS`, matching the file's existing hook shape.
- [x] 3.2 In `frontend/src/api/events.ts`, invalidate the `["gameday"]` prefix key whenever scope is `teams` or a `team:`/`h2h:` prefixed scope — alongside the existing `day-rings` escape hatch at line ~86, not via `queryKeyForScope` (design D9).
- [x] 3.3 Add `GameDayLayout` and `gameDay: GameDayLayout` to `frontend/src/stores/ui.ts` with a `GAME_DAY_DEFAULTS` const, setters for mode/order/spans/openIds/sortMode, and `gameDay` added to `partialize`. `openIds` is `string[]`, never a `Set`.
- [x] 3.4 Write `frontend/src/screens/GameDay/arrangement.ts` — pure functions for `reconcileOrder(persisted, liveIds)` (drop departed, **append new**), `applySort(ids, byId, sortMode)`, and `reorder(ids, dragId, targetId)`. Keep it free of React so it is directly unit-testable.

## 4. Frontend — view (lane C; builds against 1.4's fixture)

- [x] 4.1 `screens/GameDay/useLeadFlip.ts` — fires on a sign change of the margin only, never on magnitude. Model it on `hooks/useChangedValuePulse.ts`, including the animation-end + timeout cleanup pattern.
- [x] 4.2 `screens/GameDay/MirroredRoster.tsx` — one row per slot, both sides outward from the center cell. Orient via the existing `orientSlot()` from `screens/HeadToHead/orientation.ts`; do not re-derive the ternary. Row flash via `useChangedValuePulse`. `pre` state renders dimmed.
- [x] 4.3 `screens/GameDay/GameDayPanel.tsx` — meta row, score row with margin chip, stat strip, disclosure control, roster. **Render the roster unconditionally** (design D3); the disclosure sets a `data-roster` attribute, it does not gate the mount.
- [x] 4.4 In 4.3, derive the live border from `home_is_live || away_is_live` across slots and the settled dim from `matchup.is_complete` — **not** from `game_state` comparisons, which are null for discovery-written rows and would never dim (design D4).
- [x] 4.5 `screens/GameDay/index.tsx` — control bar (arrangement buttons, sort segmented control, expand/collapse all), the stage with `data-layout`, drag-reorder wiring, and per-panel resize. Bind reorder to the panel header and resize to the corner handle so the gestures do not collide.
- [x] 4.6 Spotlight overlay in 4.5 — click or double-click header to open, Escape or backdrop click to close, panel renders at spotlight density with roster shown.
- [x] 4.7 `screens/GameDay/GameDaySkeleton.tsx` — panel skeletons matching loaded geometry per arrangement, following the `H2HSkeleton` approach in `screens/HeadToHead/index.tsx:27`.
- [x] 4.8 Wire `EmptyState` / `ErrorCard` via `usePlatformsDisconnected`, matching how Dashboard and Head-to-Head do it.
- [x] 4.9 Add `/gameday` to `frontend/src/routes.tsx` and a `NavLink` to `components/shell/Sidebar.tsx` between Dashboard and the "My Teams" group — a direct link, not a `primaryTeamId` link.

## 5. Styles (lane C, parallel with 4)

- [x] 5.1 Port the prototype's `gameday.css` to `frontend/src/styles/gameday.css`, replacing every literal color with a token from `tokens.css` (no hex outside `tokens.css`). *(Authored from design.md D1–D4 + `specs/game-day/spec.md` — `design/gameday.css` does not exist in this repo or its git history. No hex anywhere in the file.)*
- [x] 5.2 Implement the container-query ladder: `container-type: inline-size` on the panel, breakpoints at 360 / 540 / 900px driving score size, player-name size, NFL-team visibility, and roster display.
- [x] 5.3 Add the `[data-roster="open"|"shut"]` overrides that let the disclosure button beat the container query in both directions.
- [x] 5.4 Add the four attention cues: row flash, lead-flip double-pulse, live border + glow, settled dim at 52% with hover restore. Confirm the live dot is the only continuous animation and honor `prefers-reduced-motion`.
- [x] 5.5 Set the Game Day `--aurora-color` alongside the other screens' entries.

## 6. Shared model change (lane D — independent, small)

- [x] 6.1 Add `clamp?: boolean` (default `true`) to `computeProjectedFinal` in `screens/HeadToHead/projectedFinal.ts`. Update the comment block to say why the floor exists and why Game Day opts out. Pass `clamp: true` explicitly at the Head-to-Head call sites so the intent is visible.

## 7. Tests

- [x] 7.1 `tests/api/test_teams.py` — `/api/teams/game-day` envelope shape, week defaulting, both home and away orientation, empty-when-nothing-connected, and that the path reaches the bulk handler rather than falling through to `get_team` with `team_id="game-day"`.
- [x] 7.1b Backend test that a past-week request returns that week's `score` / `opp_score` / `opp_team_name`, not the current week's.
- [x] 7.2 Backend test that `MatchupSlot` per-side state matches the corresponding `RosterSlot` rows, including a case where the two platforms label slots differently (guards the 2.1 join key).
- [x] 7.3 `projectedFinal.test.ts` — add cases for `clamp: false` returning sub-50 values, and assert the default still floors at 50.
- [x] 7.4 `arrangement.test.ts` — `reconcileOrder` drops departed ids **and appends new ones**; `applySort` orders correctly for both modes; `reorder` moves the dragged id to the target index.
- [x] 7.5 `useLeadFlip.test.tsx` — fires on sign change only, not on magnitude change; does not fire on first render.
- [x] 7.6 `MirroredRoster.test.tsx` — correct side per `iAmHome`; `pre` state renders dimmed rather than as a real zero.
- [x] 7.7 `GameDay.test.tsx` — one panel per matchup; arrangement switch changes `data-layout`; drag reorder mutates order and resets `sortMode` to `"manual"`; roster markup is present in the DOM at every arrangement.
- [x] 7.8 `GameDay.test.tsx` — panel dims when `is_complete` is true even with all `game_state` values null (regression guard for design D4).
- [x] 7.9 Snapshot the four density bands by setting explicit panel widths. *(Implemented as an identical-structure assertion + snapshot at four widths. jsdom does not evaluate `@container`, so four density snapshots would be byte-identical and pass while proving nothing; design.md's Risks section already assigns the CSS ladder itself to the visual-diff pass (8.4). The test asserts what a unit test can prove — that no width-measuring JS decides anything, so width can only change CSS. See the comment on the `GameDay density bands` block.)*

> **Three contract deviations were made during implementation, and the affected spec
> deltas in `specs/` were edited to match** — those files are what gets applied into
> `openspec/specs/` on archive, so leaving the notes only here would have archived
> requirements that contradict the code:
>
> 1. **Join key** is `(team_id, week, player_id)`, not `(player_id, week)`. D6's premise
>    was wrong: `roster_slots` is unique per *team*-week-player, so the unscoped join
>    resolves the wrong league's state for a player rostered twice. `design.md` D6 and
>    the `fantasy-data-model` "Live state joins on player identity" scenario are corrected.
> 2. **`i_am_home` added to `GameDayMatchup`.** `MatchupSlot` carries no team ids, so
>    without it the spec's own required `orientSlot(slot, iAmHome)` has no input. Added
>    to the "Bulk game-day matchups" field list with its own scenario.
> 3. **`shutIds` added to `GameDayLayout`.** The disclosure override is three-valued
>    (open / shut / no preference); one list cannot express "shut", which made
>    "overrides the container query in both directions" unreachable for a panel the
>    query had opened. Added to the "Persisted shape" scenario with its own scenario.
>
> Also: the row-flash duration is 900ms, not the design table's 1.2s —
> `useChangedValuePulse` clears its attribute on a 900ms timer, so a longer CSS
> animation is cut off mid-cycle. The design table and spec scenario now say so.

## 8. Acceptance

> **Deferred — none of these are completable from this environment.** Every item needs
> either a browser (DevTools request counts, visual diff), the iMac deployment
> (`launchctl` restart, live-window observation, RSS/CPU), or a real additional league
> connected to a platform account. They are left unchecked deliberately rather than
> marked done on the strength of the unit tests, which cover different properties.
> 8.1 has a unit-test analogue (`GameDay.test.tsx` asserts one `/game-day` request and
> no `/h2h` call) but that is not the same as counting requests on a live SSE tick.
> 8.4 additionally has no prototype to diff against — see the note on 5.1.

- [ ] 8.1 Confirm one network request per SSE tick on `/gameday` (DevTools), not twelve.
- [ ] 8.2 Set a layout (arrangement + order + a resized panel + a disclosure override), restart the app via `launchctl`, and confirm it is restored exactly.
- [ ] 8.3 Connect an additional league and confirm its panel appears without clearing `gridiron-ui-tweaks`.
- [ ] 8.4 Visual-diff Game Day against the prototype at 2-across, 3-across, 4-column, and spotlight; confirm no meaningful value renders below 15px at any density.
- [ ] 8.5 During a live window, confirm on the iMac: rows flash on scoring, a lead flip pulses its panel, settled panels dim and restore on hover, and steady-state RSS/CPU stay within the scaffold-gridiron 11.5 budget.
