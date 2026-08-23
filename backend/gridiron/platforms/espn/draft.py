"""ESPN endpoints the Draft Assistant needs, kept apart from `EspnClient`'s cached paths.

Two deliberate separations from `client.py`:

1. **`players_wl` needs no auth and no league id.** It is a public season-wide player
   index, so `fetch_player_universe()` uses a plain `httpx.AsyncClient` rather than an
   `EspnClient` — board matching must work before the user has connected any credentials
   (the board-import spec requires the import to succeed offline, with every
   `espn_player_id` NULL, rather than failing).
2. Nothing here goes through `EspnClient._cached_league_fetch`. Its TTLs are 1-24 hours,
   which is correct for rosters and fatal for draft state; the phase-5 poller lands here
   for the same reason.

Payload shape confirmed against a real 2026 fetch (fixture:
`tests/fixtures/espn/draft/players_wl.json`) — see design.md Open Question 2.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from backend.gridiron.platforms.espn.mapper import PRO_TEAM_MAP

PLAYERS_WL_BASE = "https://lm-api-reads.fantasy.espn.com"

# `players_wl` returns *every* player including IDP. These are the only positions this
# app drafts; anything else is dropped so the matcher's candidate space stays small.
DRAFTABLE_POSITION_IDS: dict[int, str] = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

DST_POSITION_ID = 16

# D/ST ids are negative and deterministic: `id == DST_ID_BASE - proTeamId`
# (Falcons -16001 ... Texans -16034). Recorded here because it is the only stable way to
# recognize a defense when the payload carries no position string.
DST_ID_BASE = -16000


@dataclass(frozen=True)
class EspnPlayerRef:
    """One entry from the player index, reduced to what board matching keys on."""

    espn_player_id: int
    full_name: str
    position: str
    nfl_team: str
    is_dst: bool


def players_wl_path(year: int) -> str:
    return f"/apis/v3/games/ffl/seasons/{year}/players"


def parse_player_universe(payload: Any) -> list[EspnPlayerRef]:
    """Reduce a raw `players_wl` payload to draftable `EspnPlayerRef`s.

    The endpoint returns a **flat JSON array**, not an object with a `players` key — a
    dict is tolerated (and its `players` list used) only so a future payload change
    doesn't hard-fail the import.
    """
    entries = payload if isinstance(payload, list) else payload.get("players", [])

    refs: list[EspnPlayerRef] = []
    for entry in entries:
        position = DRAFTABLE_POSITION_IDS.get(entry.get("defaultPositionId"))
        if position is None:
            continue
        # No abbreviation ships in this payload — only `proTeamId`. `PRO_TEAM_MAP` is
        # complete for all 32 clubs precisely so this never silently degrades to "FA",
        # which would demote an exact match to a name-only one.
        nfl_team = PRO_TEAM_MAP.get(entry.get("proTeamId", 0), "FA")
        refs.append(
            EspnPlayerRef(
                espn_player_id=int(entry["id"]),
                full_name=entry.get("fullName") or "",
                position=position,
                nfl_team=nfl_team,
                is_dst=entry.get("defaultPositionId") == DST_POSITION_ID,
            )
        )
    return refs


async def fetch_player_universe(
    year: int, *, http_client: httpx.AsyncClient | None = None
) -> list[EspnPlayerRef]:
    """Fetch and parse the season player index. No cookies, no league id required."""
    client = http_client or httpx.AsyncClient(base_url=PLAYERS_WL_BASE, timeout=30)
    try:
        response = await client.get(
            players_wl_path(year),
            params={"scoringPeriodId": 0, "view": "players_wl"},
            headers={"x-fantasy-filter": '{"filterActive":{"value":true}}'},
        )
        response.raise_for_status()
        return parse_player_universe(response.json())
    finally:
        if http_client is None:
            await client.aclose()
