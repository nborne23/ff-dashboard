## MODIFIED Requirements

### Requirement: Frontend live-update protocol

The frontend SHALL consume `/api/events` via `EventSource` and translate `data.changed` scopes into TanStack Query invalidations, so updates render within ~1 second of a cache write. Timer-based polling SHALL exist only as a degraded fallback.

#### Scenario: Scope-to-query mapping

- **WHEN** a `data.changed` event arrives with scopes
- **THEN** the client invalidates the TanStack Query keys matching those scopes for the currently-viewed week only (`teams` → `['teams', week]`; `team:{id}` → `['team', id, week]` and its h2h/season variants), triggering refetches from the local REST API.

#### Scenario: Cross-team views invalidate by prefix

- **WHEN** a `data.changed` event arrives with scope `teams` or any `team:{id}` / `h2h:{id}` scope
- **THEN** the client additionally invalidates the `['gameday']` prefix key. Game Day spans every team and so does not map to a single scope; invalidating by prefix causes one refetch of the bulk envelope per tick rather than one per team.

#### Scenario: Reconnect and fallback

- **WHEN** the SSE connection drops (process restart, phone sleeping, network change)
- **THEN** `EventSource` reconnects with backoff; while disconnected longer than 30 s the sidebar footer shows "Live connection lost — retrying" and a 5-minute `refetchInterval` fallback activates. On `visibilitychange` to visible, the client refetches active queries immediately and re-establishes the stream.

#### Scenario: Past weeks are static

- **WHEN** the user is viewing a week older than the current week
- **THEN** `data.changed` events do not invalidate that week's queries — historical data is immutable and refetching it is wasted work.
