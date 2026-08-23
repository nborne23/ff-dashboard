"""`platforms/espn/draft.py` — parsed against the real `players_wl` capture.

The fixture is the genuine public 2026 payload (no auth, no league id, no personal
identifiers), trimmed to the draftable positions. Asserting against it rather than a
hand-written stub is the point: the shape here — a flat array, no team abbreviation,
negative deterministic D/ST ids — is exactly what a hand-written stub got wrong before
the capture existed.
"""

import json
from pathlib import Path

import httpx
import pytest

from backend.gridiron.platforms.espn.mapper import PRO_TEAM_MAP
from backend.gridiron.platforms.espn.draft import (
    DST_ID_BASE,
    EspnPlayerRef,
    fetch_player_universe,
    parse_player_universe,
    players_wl_path,
)

FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures/espn/draft/players_wl.json"


@pytest.fixture
def payload() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def test_payload_is_a_flat_array(payload):
    assert isinstance(payload, list)


def test_parses_every_draftable_entry(payload):
    refs = parse_player_universe(payload)
    assert len(refs) == len(payload)
    assert all(isinstance(r, EspnPlayerRef) for r in refs)


def test_idp_entries_are_dropped():
    refs = parse_player_universe([{"id": 1, "fullName": "LB Guy", "defaultPositionId": 11}])
    assert refs == []


def test_every_rostered_pro_team_id_maps_to_an_abbreviation(payload):
    """No entry on an NFL roster may fall through to "FA".

    "FA" is a legitimate value — `proTeamId == 0` means genuinely unsigned, and 205 of
    the 1,027 draftable entries are, this being August. That is exactly why a *partial*
    `PRO_TEAM_MAP` was dangerous: an unmapped club is indistinguishable from a real free
    agent at the call site, and would quietly demote an exact match to a name-only one.
    So assert on the ids rather than on a rate.
    """
    unmapped = {
        entry["proTeamId"]
        for entry in payload
        if entry.get("proTeamId") and PRO_TEAM_MAP.get(entry["proTeamId"]) is None
    }
    assert unmapped == set()

    refs = parse_player_universe(payload)
    free_agents = [r for r in refs if r.nfl_team == "FA"]
    assert all(
        e.get("proTeamId", 0) == 0
        for e in payload
        if e["id"] in {r.espn_player_id for r in free_agents}
    )


def test_dst_entries(payload):
    refs = [r for r in parse_player_universe(payload) if r.is_dst]
    assert len(refs) == 32
    for ref in refs:
        assert ref.position == "DST"
        assert ref.espn_player_id < 0
        assert ref.full_name.endswith("D/ST")
    # Deterministic id encoding: `id == DST_ID_BASE - proTeamId`.
    atlanta = next(r for r in refs if r.nfl_team == "ATL")
    assert atlanta.espn_player_id == DST_ID_BASE - 1
    # The name is the club *nickname*, never the city — which is why DST matching keys
    # on the team abbreviation and never attempts a name method.
    assert atlanta.full_name == "Falcons D/ST"


def test_dict_payload_is_tolerated():
    refs = parse_player_universe({"players": [{"id": 5, "fullName": "X", "defaultPositionId": 1}]})
    assert [r.espn_player_id for r in refs] == [5]


async def test_fetch_player_universe_uses_no_cookies(payload):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, json=payload[:5])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as client:
        refs = await fetch_player_universe(2026, http_client=client)

    assert len(refs) == 5
    assert seen["cookie"] is None
    assert players_wl_path(2026) in seen["url"]
