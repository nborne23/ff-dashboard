## Context

GridIron runs unattended on a 2019 iMac behind a LaunchAgent, reachable over Tailscale. Its Sunday mode is a wall display: full screen, read from ten to twenty feet, nobody scanning the numbers continuously. Every existing screen was designed for a laptop at arm's length.

The pieces Game Day needs mostly exist. `Team` already carries `record`, `rank`, `current_score`, `current_opp_score`, `current_opponent_name`, and `is_live`. `Matchup` carries `is_complete` and both projections. `RosterSlot` carries `is_live` and `game_state`. `HeadToHead/orientation.ts` already solves "the route's team can be on either side". `useChangedValuePulse` already flashes changed values. What is missing is a way to get all of it in one request, per-side live state on the *matchup* slots, and a component that reads at six-panels-per-screen density.

Three constraints drive every decision below:

1. **Type scales up, not down.** No value that matters below 15px; scores reach 46–64px.
2. **Layout is configured once, then left alone.** Interaction is for setup, not for reading.
3. **Change must be visible without being read.** Motion and color carry the "something happened" signal.

## Goals / Non-Goals

**Goals:**

- Every matchup's *complete* head-to-head visible simultaneously, at four densities, from one component.
- One request per refresh tick instead of twelve.
- Layout survives an app restart.
- Attention cues that distinguish "settled" from "in play" without moving anything on screen.

**Non-Goals:**

- Red-zone cues (needs new ingestion + a migration — deferred to `add-nfl-redzone`).
- Bench players, per-panel rings, cross-league aggregate scoring.
- Any change to Head-to-Head's rendered output. `projectedFinal.ts` gains an option; its existing behavior is preserved explicitly at the call site.

## Decisions

### D1. Panel anatomy — one component, four densities

```
┌────────────────────────────────────────────────────────┐
│ [YAHOO] Highland Bombers · Highland Bros Dynasty   ●3 ⤢ │  meta + live pill
│                                                        │
│  HIGHLAND BOMBERS      ┌────────┐      TOUCHDOWN CLUB  │  names: --move / --stand
│       87.4             │ +16.2  │           71.2       │  values: white / dimmed
│                        │ 8–3 · 2 of 12 │               │  margin chip carries sign
├────────────────────────────────────────────────────────┤
│ PROJECTED       WIN PROB        YET TO PLAY            │  stat strip
│ 113 vs 98       82%             3 vs 5                 │
├────────────────────────────────────────────────────────┤
│                  ⌄ FULL MATCHUP                        │  disclosure
├────────────────────────────────────────────────────────┤
│ ● P. Mahomes  KC  19.8 ┊  QB  ┊ 23.4  BUF  J. Allen    │  mirrored rows
│   B. Robinson ATL 24.1 ┊ +3.6 ┊ 18.2  PHI  S. Barkley  │
└────────────────────────────────────────────────────────┘
```

**Score identity.** My team is `--move` (pink), the opponent `--stand` (cyan) — the assignment Head-to-Head already uses, so two screens teach one color rule. Only the *labels* carry color; score values stay white, and the trailing side drops to `--text-secondary`. "Who is winning" is then legible as a brightness difference at twenty feet, before any number is read.

**Margin chip** sits between the scores and is the only place lead/deficit is stated outright.

*Alternative rejected:* coloring the winning score green. It collides with the app's category palette (values are white everywhere else per `gridiron-ui`'s pixel-fidelity requirement) and reads as a status badge rather than a comparison.

### D2. Mirrored roster rows

Each slot is one row, both teams on it, reading outward from a dashed center rule that holds the slot label and per-slot differential.

Head-to-Head's three-column table needs ~900px to avoid truncating names. A 3-across or 4-column panel gets 340–520px. Mirroring keeps both names full-length by spending width on text instead of a third structural column; the dashed rule and differential chip preserve the "these two are opposed" reading.

Rows reuse `orientSlot(slot, iAmHome)` from `HeadToHead/orientation.ts` unchanged — Game Day must not re-derive the home/away ternary.

### D3. Density via container queries — and the roster renders unconditionally

The panel declares `container-type: inline-size`, so density follows the panel's own width, not the viewport and not a prop:

| Panel width | Arrangement | Score | Player name | Roster |
| --- | --- | --- | --- | --- |
| < 360px | 4-column | 26px | 12px, NFL team hidden | hidden |
| 360–539px | 3-across | 32px | 13px | hidden |
| ≥ 540px | 2-across | 46px | 15px | **shown** |
| ≥ 900px | spotlight | 64px | 17px | shown |

This resolves the tension between "roster on demand" and "no interaction expected": a panel reveals its roster once it is wide enough to read, and a manually widened panel inherits that for free.

**The consequence that matters:** CSS cannot set React state, so "default open at ≥540px" cannot be a `useState` initializer. The roster is therefore **always rendered** and hidden by `@container` below 540px; the disclosure button toggles a class that overrides the query, not a mount.

```
        ┌─ ALWAYS RENDERED ─────────────────────────┐
        │  <div class="gd-roster">  9 rows          │
        └───────────────┬───────────────────────────┘
                        │
      @container (max-width: 539px) → display: none
                        │
      [data-roster="open"]  overrides → display: block   ← the button
      [data-roster="shut"]  overrides → display: none
```

*Alternative rejected:* `ResizeObserver` per panel feeding React state. It reintroduces exactly the width plumbing container queries exist to delete, and makes the density ladder live in two places. Cost of always rendering: 6 panels × 9 rows = 54 rows of DOM. Negligible.

*Alternative rejected:* the prototype's `GD_AUTO_OPEN = { g2: true, g3: false, … }` layout-keyed map. It keys off the arrangement rather than the actual width, which is why the prototype also needs the `open={openIds.has(id) || sp.cols === 2}` patch for manually widened panels. The container query subsumes both.

### D4. Attention model — four cues, four event classes

| Event | Cue | Source of truth | Duration |
| --- | --- | --- | --- |
| A player's points change | Row flashes `--live` 26% → transparent | `useChangedValuePulse(pts)` | 0.9s (the hook's `PULSE_ANIMATION_MS`; it clears the attribute on that timer, so a longer CSS duration would be cut off) |
| A lead flips | Panel double-pulses `--move` 22% | `useLeadFlip(margin)` (new) | 1.4s |
| Any player in the panel is live | Border `--live` 45% + soft glow | **`slot.home_is_live \|\| slot.away_is_live`** | persistent |
| All games in the panel final | Panel drops to 52% opacity | **`matchup.is_complete`** | persistent |

The last two are the correction the prototype needs. Deriving them from `game_state` is wrong:

```
   discovery writes RosterSlot rows with game_state = NULL
                         │
   "all final" = every slot state === "post"
                         │
              NULL !== "post"  →  always false
                         ▼
              PANELS NEVER DIM  ✗
```

`_remaining_count` in `fantasy_service.py` already documents this NULL-means-unclassified behavior and guards against it. `Matchup.is_complete` and `RosterSlot.is_live` are populated and authoritative; use them. `home_state`/`away_state` are still carried — they are what distinguishes "0.0, hasn't played" from "0.0, shut out" on an individual row — but they do not drive panel-level state.

**Dimming is the load-bearing cue.** By late Sunday most panels are settled; dropping them back lets the two still in play own the screen without anything moving. Hovering a dimmed panel restores it.

The live dot is the only continuous animation, and it is one small dot. No panel animates position except during an explicit sort change.

### D5. `GET /api/teams/game-day` — one envelope

```
   BEFORE                              AFTER
   6 × /api/teams/{id}/h2h             1 × /api/teams/game-day?week=
   6 × /api/teams/{id}       ─────▶    ┌──────────────────────────┐
   ────────────────────                │ matchups: [              │
   12 requests per SSE tick            │   { team + opp identity, │
                                       │     proj, remaining,     │
                                       │     slots[] } × 6 ]      │
                                       └──────────────────────────┘
                                       1 request per SSE tick
```

**Named `/game-day`, not `/h2h`.** A bare `/api/teams/h2h` sits beside `/api/teams/{team_id}/h2h` and reads as "the head-to-head of a team called h2h". `/game-day` parallels the existing `/day-rings`, which also establishes the precedent that matters here: **register it before `/{team_id}`** or FastAPI matches the path parameter first (`teams.py:55`).

**Reuse `_team_schema`, don't rebuild it.** Most of `GameDayMatchup` already exists on `Team`:

| Field | Source |
| --- | --- |
| `team_name`, `record`, `rank`, `score`, `opp_score`, `opp_team_name` | `Team` (already computed) |
| `league_name` | join `League` |
| `proj`, `opp_proj`, `is_complete` | `Matchup` |
| `remaining` | `_remaining_count` × 2 |
| `platform` | **id prefix** — `Team` has no `platform` field (see below) |
| `slots` | `MatchupSlot` + the new per-side state |

Two traps in that table:

- **`platform` is not on `Team`.** The meta-row pill needs it, but the entity carries only `id`, `league_id`, `name`, `manager_name`, `record`, `rank`, `points_for`, `points_against`, `is_user_team`, `current_score`, `current_opp_score`, `current_opponent_name`, `is_live`, `spark_last_6`, `accent_color`. Split it off the `{platform}:{platform_id}` id the way `Sidebar.tsx:83` already does.
- **`is_complete` comes from `Matchup`, and D4's dim cue hangs entirely on it.** It is the one field in this table with no fallback.

`_team_schema(session, row, week)` is genuinely week-scoped — its `Matchup` lookup filters on `Matchup.week == week`, so `current_score` / `current_opp_score` / `current_opponent_name` are the requested week's values, not the current week's. Reusing it for a past week is safe.

`game_day()` is one query pass over all user teams — no N+1. Same `Cache-Control` as the rest of `api/teams.py`, same read-only-from-normalized-tables rule.

### D6. Per-side live state joins on `player_id`, not `slot`

`MatchupSlot` has `matchup_id`, `slot`, `home_player_id`, `away_player_id` — no `team_id`. The state lives on `RosterSlot(team_id, week, slot, player_id)`. The join key is the decision:

```
   ✗ join on (matchup.home_team_id, week, slot)
     Yahoo:  _pair_matchup_slots() builds MatchupSlots BY slot label from RosterSlots
     ESPN:   espn.mapper.map_matchup() produces MatchupSlots natively
     → the two paths do not guarantee the same slot labeling

   ✓ join on (RosterSlot.team_id == <that side's team>, week, player_id)
     player identity is platform-independent; the team id scopes it because
     roster_slots is unique per TEAM-week-player (uq_roster_slots_team_week_player),
     not per player-week — a player rostered in two of the user's leagues has a
     row per team, so an unscoped join resolves the wrong league's state.

     [Corrected during implementation. This decision originally claimed
     (player_id, week) was itself uniquely constrained, citing migration
     a3c1f0d47e21_roster_slots_unique_per_player; that migration's uniqueness is
     per player *within a team-week*. The rejected alternative below — the slot
     label as join key — is unaffected and still rejected.]
```

Fields added to the `MatchupSlot` **Pydantic schema only** — `home_state`, `away_state` (`GameState | None`), `home_is_live`, `away_is_live` (`bool`). **No migration:** every value already sits in `roster_slots`.

### D7. Win probability — one implementation, one file

`computeProjectedFinal` clamps to `[50, 99]` deliberately: *"it always reads >= 50 (a 'floored, favorite view'), even when the raw model favors the opponent — this mirrors the prototype's confidence badge, which never shows 'my team probably loses.'"*

That is right for one matchup and actively misleading for six. Six panels each reading ≥50% tells the user they are favored in every league while two are lost.

Decision: add `clamp?: boolean` (default `true`, preserving current behavior for any caller). Head-to-Head passes it explicitly for legibility; Game Day passes `false`.

`win_prob` is consequently **dropped from the envelope**. The endpoint already returns `proj`, `opp_proj`, and `remaining` — the function's only three inputs — so a server-side copy would mean porting a JS-tuned logistic approximation into Python and keeping two test suites in sync for no gain. This closes the source plan's open question 5.1.

### D8. Layout persistence and reconciliation

```ts
interface GameDayLayout {
  mode: "g2" | "g3" | "c4" | "spot";
  order: string[];                              // team ids
  spans: Record<string, { cols: 1 | 2; rows: 1 | 2 }>;
  openIds: string[];                            // manual roster overrides
  sortMode: "manual" | "margin" | "live";
}
```

Persisted to `stores/ui.ts` under the existing `gridiron-ui-tweaks` key and added to `partialize`. `openIds` is an array, not a `Set` — `Set` does not survive JSON.

**Reconciliation on read** is the part the prototype gets half right. `order.filter(id => byId[id])` drops teams that disappeared, but silently omits ones that appeared — connect a new league and its panel never renders. Order must be reconciled in both directions: drop unknown ids, then append live ids not already present.

Drag-to-reorder sets `sortMode` back to `"manual"` implicitly. An auto-sort mode and a hand-placed order are mutually exclusive states, not layers.

### D9. SSE invalidation uses the `day-rings` escape hatch

`queryKeyForScope()` maps one scope to one key prefix. Game Day spans every team, so it does not fit that map — it must invalidate on scope `teams` *and* on any `team:{id}`/`h2h:{id}`. `events.ts:86` already established this shape for the Topbar's day rings:

```ts
if (scope === "teams") void queryClient.invalidateQueries({ queryKey: ["day-rings"] });
```

Game Day gets the same treatment against `["gameday"]` — a prefix key, so `["gameday", week]` matches without enumerating weeks. One refetch per tick instead of twelve.

## Risks / Trade-offs

**Six panels × 9 rows re-render on every SSE tick** → The envelope is one query key, so a tick replaces one cache entry and React reconciles ~54 rows. Well within budget for the 2019 iMac (scaffold task 11.5 targets < 300 MB RSS, near-zero idle CPU), but worth watching during the acceptance pass: if it shows up, memoize `GameDayPanel` on its matchup object.

**Container queries put the density ladder in CSS, out of reach of JS tests** → Test by setting explicit panel widths in the test DOM and asserting rendered structure, not by mocking a breakpoint. jsdom does not evaluate `@container`, so the CSS ladder itself is verified in the visual-diff pass, and the *unconditional render* is what unit tests assert.

**`is_complete` may lag on a platform that reports it late** → Dimming is a soft cue; a panel that dims a tick late costs nothing. Preferred over the alternative failure mode of never dimming at all.

**A persisted layout can outlive its teams entirely** (all leagues disconnected, then reconnected with new ids) → Reconciliation is append-and-drop, so a fully-replaced team set produces default order rather than an empty stage. `usePlatformsDisconnected` covers the genuinely-empty case with `EmptyState`.

**Adding a sixth screen touches a spec that says "exactly five"** → `gridiron-ui`'s "Five-screen application shell" requirement is modified here rather than worked around, so the spec and the router stay in agreement.

**Drag-and-drop via native HTML5 events** (as prototyped) is awkward with pointer-based resize on the same element → Resize is bound to a corner handle with `stopPropagation` on `pointerdown`; drag is bound to the panel header only, not the body. Keeps the two gestures on disjoint targets.

## Migration Plan

No data migration. All schema additions are additive Pydantic fields over existing columns; all frontend changes are new files plus additive edits. Rollback is reverting the commit — no persisted state changes shape, and an unrecognized `gameDay` key in `gridiron-ui-tweaks` is ignored by the older store.

## Open Questions

- Whether the spotlight overlay should pause auto-sort while open. Sorting a panel out from under a user who is deliberately staring at it is jarring; sorting is currently only triggered by explicit mode changes, so this is latent rather than active. Revisit if auto-sort is ever made continuous.
