# Design — add-player-health

## D1. Which upstream API supplies the health detail

Four candidates were probed live (2026-09-02) before choosing:

| Endpoint | Auth | Verdict |
| --- | --- | --- |
| `sports.core.api.espn.com/v2/.../seasons/{season}/athletes/{id}/injuries` | none | **Chosen.** Full detail. |
| `sports.core.api.espn.com/v2/.../athletes/{id}` | none | Carries `status` only (`{"name":"Day-To-Day"}`) — strictly less than the injuries collection, so unused. |
| `site.api.espn.com/.../teams/{team}/roster?enable=injuries` | none | 32 calls covers the league, but each entry is `{status, date}` — no detail, no comment. Rejected: it duplicates what the fantasy API already gives us. |
| `site.web.api.espn.com/apis/common/v3/.../athletes/{id}` | none | Bio/stats. No injury detail. |

A real response (Ricky Pearsall, athlete 4428209):

```json
{
  "id": "633398",
  "status": "Injured Reserve",
  "date": "2026-08-13T15:11Z",
  "type":    { "name": "INJURY_STATUS_IR", "description": "Injured Reserve", "abbreviation": "IR" },
  "details": { "type": "Knee - PCL", "location": "Leg", "detail": "Surgery",
               "side": "Right", "returnDate": "2027-02-15",
               "fantasyStatus": { "abbreviation": "IR" } },
  "shortComment": "Pearsall announced Thursday ... underwent season-ending surgery ...",
  "longComment":  "The procedure typically carries a wide-ranging recovery timeline ..."
}
```

Two traps this endpoint sets:

- **The season year is load-bearing.** The same athlete returns `count: 0` for
  `seasons/2025` and the report above for `seasons/2026`. The season comes from
  `max(League.season)`, falling back to `fantasy_service._current_season()` — never a literal.
- **`count: 0` is the normal healthy answer**, not an error. It must not be logged as one.

## D2. Cache-only reads (design.md D7 holds)

`GET /api/players/{id}/injury` never calls ESPN. The `refresh_injuries` scheduler job owns
every upstream call and writes `player_injuries`; the read serves whatever is there, or
`report: null`. This is the `refresh_player_pool` pattern, not the `headshots` one —
headshots fetch on miss because they are immutable binary assets with a permanent negative
cache, which injury prose is not.

Cadence is a fixed 30 minutes, deliberately not bound to the live tier: injury reports are
filed on practice-report and gameday-inactive schedules, not on snap-by-snap ones.

## D3. Who gets swept

Only players whose fantasy `injury_status` is set and not `ACTIVE`. That is ~130 rows on
this install against a 1030-row `players` table, and it collapses to near zero in the
off-season.

Two id classes are skipped outright, both of which would 404:

- D/ST rows carry synthetic negative ids (`espn:p--16007`) — there is no such athlete.
- Yahoo-sourced players (`yahoo:p-...`) have no ESPN athlete id, and no cross-platform id
  map exists yet. Their badge still renders from the fantasy status; only the detail panel
  is unavailable, and it says so rather than showing an error.

## D4. Vocabulary

`ACTIVE|Q|D|O|IR|PUP|DTD|SUSP|NFI`.

`PROBABLE` is deliberately absent — the NFL retired it from the injury report in 2016.
`NORMAL` is ESPN's healthy sentinel and maps to `ACTIVE`. Anything unrecognized maps to
`None` and logs at WARNING: this install's cache only covers 12 preseason teams, so absence
from it is not evidence of absence from ESPN, and a silent wrong answer is worse than a gap.

## D5. Badge placement

The badge sits next to the position pill inside `player-info-row`, **not** in the roster
Status column. That column is an `is_live ? … : isOut ? … : status_text` chain; extending
it to Q/D/IR would replace kickoff time for every questionable player — a strict loss of
information on exactly the rows the user is deciding about.

Every badge is a letter code plus a color, never color alone.
