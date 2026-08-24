## 0. The blocking question

> **This gates everything below.** If picks do not appear mid-draft, cut the change.

- [ ] 0.1 During a live ESPN draft, poll `mDraftDetail` for the real league and record whether `playerId` populates before the draft completes. Commit the mid-draft payload as `tests/fixtures/espn/draft/mdraftdetail_inprogress.json`, scrubbed of the league ID and personal identifiers.
- [ ] 0.2 Capture `kona_player_info` for the off-board tail (task 4.1), scrubbed the same way.

## 1. Poller

- [ ] 1.1 `platforms/espn/draft.py`: `fetch_draft_detail()` calling `EspnClient.get()` **directly**, never `_cached_league_fetch`. Comment the call site naming the stale-cache failure mode. Count picks by `playerId != -1` — the array is pre-populated with 150 shells before the draft starts, so length means nothing.
- [ ] 1.2 Regression test asserting a draft fetch creates **no** `http_cache` row, so a future consolidation of ESPN fetch paths cannot reintroduce a 1-6 hour TTL on a 3-second poll.
- [ ] 1.3 `run_job(audit: bool = True)`; `poll_draft` passes `False` and updates `last_poll_at`/`last_error` on its `draft_sessions` row instead. Failures still log at WARN.
- [ ] 1.4 `scheduler.py`: register `poll_draft` in `JOBS` with **no** trigger; add `arm_draft_poll()` / `disarm_draft_poll()`. Test that boot registers no trigger and the adaptive cadence is unchanged.
- [ ] 1.5 Job body: upsert picks through `draft_state.record_pick()` with `source='espn'`, record round / overall pick / on-the-clock team, publish the `draft` scope only on change.
- [ ] 1.6 Reconciliation: ESPN wins on identity at a conflicting `overall_pick` and the correction is surfaced, not silent; manual rows beyond ESPN's high-water mark are left alone; agreement upgrades `source` only.
- [ ] 1.7 Auto-disarm: three consecutive `inProgress: false` **with a complete pick set**, the `armed_at + 6h` ceiling, and explicit disarm. A single false tick SHALL NOT disarm.
- [ ] 1.8 Error handling: 429/5xx backs off to 10 s; five consecutive failures disarms with a UI-visible reason.

## 2. UI

- [ ] 2.1 `POST /api/draft/arm` / `POST /api/draft/disarm` + `screens/Draft/SessionControl.tsx` showing round, overall pick, on-the-clock team, and a loud banner when tracking stops.
- [ ] 2.2 Off-board tail from `kona_player_info` ADP ordering, visually separated and never ranked above a board player.

## 3. Acceptance

- [ ] 3.1 Arm against a live draft; picks land within ~3 s; kill the network mid-draft and confirm the session disarms loudly and manual entry continues uninterrupted.
