## Why

`add-draft-assistant` shipped the draft-night path: board import, ESPN player-ID matching, the recommendation engine, and a Draft screen driven entirely by a manual pick log. Live ESPN polling was deliberately deferred, because the one thing it depends on could not be verified in time.

What we learned probing the real ESPN API on 2026-08-23:

- `mDraftDetail` **does** carry real picks with the field names this change was designed against. The user's completed league returns 150 real picks, the first being `{overallPickNumber, roundId, roundPickNumber, teamId, playerId}` populated on every pick.
- `inProgress` **does** flip to `true` while a draft room is live, which is the arming signal.
- **A practice draft writes nothing.** With the ESPN UI showing round 6, pick 60, and ~59 players gone, the API returned all 150 pick shells at `playerId: -1` and every roster empty — across `lm-api-reads`, the `kona_draft_detail` view, `mLiveScoring`, the `/draftDetail` sub-path, and the `kona_league_communication` feed. Practice drafts are disposable and never touch real rosters, so they never persist.
- `picks` is **pre-populated with a full shell array before the draft starts** — 150 entries, every `playerId: -1`. Array length is therefore not a liveness signal; only `playerId != -1` counts.

## What Changes

Adds armed-only live polling of ESPN draft state, reconciliation against manually entered picks, and the session control UI — plus the off-board pool tail that depends on the same `kona_player_info` fetch.

The one open question that remains is narrow: whether picks land in `mDraftDetail` **during** a draft or only at completion. Task 0.1 answers it and gates everything after it. If picks only appear at completion, this change is cut and the manual path stands alone — which is why it is isolated here rather than blocking the shipped feature.

## Capabilities

- `draft-tracking` — armed-only polling, cache bypass, audit suppression, ESPN/manual reconciliation, off-board tail
- `draft-ui` — session control and tracking status

## Impact

Additive. No shipped behavior changes: the manual pick path stays primary and every polled pick is written through it.
