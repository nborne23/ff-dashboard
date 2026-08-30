## Why

The Dashboard answers "how are my teams doing" — six score lines and a sparkline each. It does not answer the question that actually matters while games are running: **for each league, who is beating me, by how much, and which players are left.** Getting that today means visiting `/team/:id/h2h` six times, losing the comparison the moment you navigate.

This app runs as a persistent local install on an iMac (`deploy/setup-imac.sh`, `com.gridiron.app.plist`). Its primary Sunday mode is **full screen, read from across the room, unattended for hours** — a mode no current screen serves. Game Day is a single view holding every matchup at once, each showing its complete head-to-head, arranged once and then left alone.

## What Changes

**New screen**

- New route `/gameday` with a sidebar entry above My Teams.
- One panel per matchup, rendering the full head-to-head: meta row, both scores with a signed margin chip, a three-stat strip (projected / win prob / yet to play), and the nine starter slots as **mirrored rows** — both teams on one line, reading outward from a dashed center rule that carries the slot label and per-slot differential.
- Four arrangements (2-across, 3-across, 4-column, spotlight), per-panel resize to span 2 columns and/or 2 rows, drag-to-reorder, click-to-spotlight with Esc to exit, and auto-sort by closest margin or most live players.
- Layout persists to the existing `gridiron-ui-tweaks` store. A wall display that forgets its layout on restart is one nobody sets up twice — and the LaunchAgent restarts this app.
- Density follows each panel's own width via container queries, not the viewport and not a prop: one component, four ladders. Scores run 26px → 64px; no value that matters drops below 15px.
- Four attention cues so change is visible without being read: per-row flash on a points change, panel double-pulse on a lead flip, a persistent live border, and — the load-bearing one — **dimming settled panels to 52%** so the two still in play own the screen by late Sunday without anything moving.

**Backend**

- New bulk endpoint `GET /api/teams/game-day?week=` returning every matchup involving one of the user's teams in one envelope, replacing 6 `/h2h` + 6 `/{id}` requests. Named to parallel the existing `/day-rings` rather than `/h2h`, which would read as "the head-to-head of a team called h2h".
- `MatchupSlot` gains `home_state` / `away_state` (`GameState`) and `home_is_live` / `away_is_live`, joined from the `roster_slots` rows that already carry them. Without per-side state the roster cannot distinguish "0.0 because he hasn't played" from "0.0 because he was shut out" — the difference between a panel that is losing and one that is about to win. **No migration: this is a Pydantic-schema change over data already persisted.**

**Frontend model**

- `computeProjectedFinal` gains a `clamp` option. Its current `[50, 99]` floor is deliberate and documented for Head-to-Head ("never shows my team probably loses"), but six panels each asserting ≥50% would tell the user they are favored in every league while two are lost. Head-to-Head keeps the floor; Game Day reads the true value. `win_prob` is therefore **not** carried on the envelope — one implementation of that number, client-side.

## Non-Goals

- **Red zone cues.** The only D4-class cue not derivable from persisted data — it needs new ESPN scoreboard parsing (`situation.isRedZone` / `situation.possession`), two new `live_nfl_games` columns, a migration, and a decision on DST inversion (a defense faces a red zone, it does not have one). Deferred to a follow-up `add-nfl-redzone` change that upgrades the cue in place.
- **Bench players in panels.** Nine starter slots × six panels is the density ceiling.
- **Per-panel ring visuals.** Rings read at one-per-screen (Head-to-Head), not six.
- **Cross-league aggregate scoring.** Different scoring types make the sum meaningless.
- **Blocking `scaffold-gridiron` v1.** Game Day is independent of that change's remaining acceptance tests; its own visual-diff pass lives here.

## Capabilities

### New Capabilities

- `game-day`: The Game Day view — panel anatomy and score identity, mirrored roster rows, the container-query density ladder, arrangement/resize/sort/persistence, the spotlight overlay, and the four-cue attention model.

### Modified Capabilities

- `fantasy-data-model`: "Read API for the frontend" gains the `GET /api/teams/game-day` bulk endpoint; "Normalized internal entities" gains per-side live state on `MatchupSlot`.
- `gridiron-ui`: "Five-screen application shell" becomes six screens, with `/gameday` routed and reachable from the sidebar.
- `live-updates`: "Frontend live-update protocol" gains `["gameday", week]` to the SSE invalidation set.

> **Archive-order dependency — `scaffold-gridiron` MUST archive before this change.**
> These three capabilities currently live in `openspec/changes/scaffold-gridiron/specs/` and only land in `openspec/specs/` when that change archives. The deltas here are written against those requirement names, so archiving this change first aborts with *"target spec does not exist; only ADDED requirements are allowed for new specs."*
>
> Verified on a throwaway copy of `openspec/`: the out-of-order archive **fails loudly and changes no files** (no silent spec loss), and the in-order chain — `scaffold-gridiron` then `add-game-day-view` — applies cleanly, preserving every pre-existing requirement in all three capabilities.

## Impact

**Backend** — `schemas/matchups.py`, `services/fantasy_service.py` (new `game_day()`, single query pass, no N+1), `api/teams.py` (register `/game-day` **before** `/{team_id}`, the same ordering trap `/day-rings` already handles), `tests/api/test_teams.py`.

**Frontend** — new `screens/GameDay/`, new `styles/gameday.css`; touches `types/api.ts`, `api/teams.ts`, `api/events.ts`, `stores/ui.ts`, `routes.tsx`, `components/shell/Sidebar.tsx`, and `screens/HeadToHead/projectedFinal.ts` (additive option; existing call site passes the current behavior explicitly).

**Reused unchanged** — `HeadToHead/orientation.ts` (`orientMatchup`/`orientSlot`), `hooks/useChangedValuePulse.ts`, `components/shared/{EmptyState,ErrorCard}`, `hooks/usePlatformsDisconnected.ts`, `components/primitives/Skeleton`.

**No migration. No new dependencies. No breaking changes** — every schema addition is additive and every existing endpoint keeps its shape.
