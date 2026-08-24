"""`/api/draft*` — the Draft Assistant read/write API (task 3.4)."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.draft_board import run_import
from backend.gridiron.models import Base, BoardHeuristic, BoardIdOverride, BoardPlayer, BoardTier
from backend.gridiron.platforms.espn.draft import EspnPlayerRef, parse_player_universe
from backend.gridiron.services import differ, draft_matches, events, fantasy_service
from backend.main import app

CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"

# See tests/services/test_draft_state.py -- read the real league shape, don't pin it.
STATIC_TEAMS: int = json.loads(
    (
        Path(__file__).resolve().parents[2] / "backend/gridiron/draft_board/league_config.json"
    ).read_text()
)["teams"]
STATIC_FLEX_SLOTS: list[str] = [
    f"FLEX{i + 1}"
    for i in range(
        json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "backend/gridiron/draft_board/league_config.json"
            ).read_text()
        )["roster"]["starters"]["FLEX"]
    )
]

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "espn" / "draft" / "players_wl.json"
)


async def _fixture_fetch_universe() -> list[EspnPlayerRef]:
    """The real committed board matched against the real (fixture-captured) ESPN
    universe -- never a live network call, matching `test_draft_board_matching.py`'s
    own end-to-end `run_import` tests."""
    payload = json.loads(FIXTURE_PATH.read_text())
    return parse_player_universe(payload)


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    differ.reset_state()
    events.reset()
    draft_matches.reset_state()
    yield
    fantasy_service.reset_state()
    differ.reset_state()
    events.reset()
    draft_matches.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "draft-api.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(db) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


async def seed_players(db) -> None:
    async with db() as session:
        session.add(
            BoardPlayer(
                name="Bijan Robinson", normalized_name="bijan robinson", position="RB", adp_rank=1
            )
        )
        session.add(
            BoardPlayer(
                name="Ja'Marr Chase", normalized_name="jamarr chase", position="WR", adp_rank=2
            )
        )
        session.add(
            BoardPlayer(
                name="Hurt Guy",
                normalized_name="hurt guy",
                position="RB",
                adp_rank=3,
                out_for_season=True,
            )
        )
        await session.commit()


async def _player_id(db, name: str) -> int:
    from sqlalchemy import select

    async with db() as session:
        row = (
            (await session.execute(select(BoardPlayer).where(BoardPlayer.name == name)))
            .scalars()
            .one()
        )
        return row.id


# ---------------------------------------------------------------------------
# /board
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_board_returns_all_players_with_drafted_flag(client, db) -> None:
    await seed_players(db)
    bijan_id = await _player_id(db, "Bijan Robinson")

    resp = await client.post(
        "/api/draft/picks", json={"board_player_id": bijan_id, "overall_pick": 1}
    )
    assert resp.status_code == 201

    resp = await client.get("/api/draft/board")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == CACHE_CONTROL
    body = resp.json()
    assert "meta" in body
    players = {p["name"]: p for p in body["data"]["players"]}
    assert players["Bijan Robinson"]["is_drafted"] is True
    assert players["Bijan Robinson"]["drafted_overall_pick"] == 1
    assert players["Ja'Marr Chase"]["is_drafted"] is False
    # Out-for-season players stay visible on the board (not removed), per task 3.4.
    assert "Hurt Guy" in players
    assert players["Hurt Guy"]["out_for_season"] is True


@pytest.mark.asyncio
async def test_get_board_exposes_full_scouting_content(client, db) -> None:
    """6.3 -- `/board` must expose sleeper_category/catalyst/format_fit/injury_tags/
    analyst_takes plus the resolved overall + positional tier LABELS (from
    `board_tiers`), not just the bare tier numbers `CandidateOut` already carried."""
    async with db() as session:
        session.add(
            BoardPlayer(
                name="Jahmyr Gibbs",
                normalized_name="jahmyr gibbs",
                position="RB",
                adp_rank=1,
                overall_tier=1,
                positional_tier=1,
                sleeper_category="ELITE",
                catalyst="Bell-cow workload",
                format_fit="Redraft",
                injury_tags=json.dumps(["mcl"]),
                analyst_takes=json.dumps(
                    [
                        {
                            "source": "The Fantasy Footballers",
                            "verified_accuracy": False,
                            "take": "RB1 overall",
                            "detail": "Consensus RB1.",
                        }
                    ]
                ),
            )
        )
        session.add(BoardTier(scope="overall", position=None, tier=1, label="TIER 1 -- ELITE"))
        session.add(BoardTier(scope="positional", position="RB", tier=1, label="TIER 1 -- RB"))
        await session.commit()

    resp = await client.get("/api/draft/board")
    assert resp.status_code == 200
    player = next(p for p in resp.json()["data"]["players"] if p["name"] == "Jahmyr Gibbs")

    assert player["sleeper_category"] == "ELITE"
    assert player["catalyst"] == "Bell-cow workload"
    assert player["format_fit"] == "Redraft"
    assert player["injury_tags"] == ["mcl"]
    assert player["analyst_takes"] == [
        {
            "source": "The Fantasy Footballers",
            "verified_accuracy": False,
            "take": "RB1 overall",
            "detail": "Consensus RB1.",
        }
    ]
    assert player["overall_tier_label"] == "TIER 1 -- ELITE"
    assert player["positional_tier_label"] == "TIER 1 -- RB"


# ---------------------------------------------------------------------------
# /slot-plan
# ---------------------------------------------------------------------------


async def _seed_slot_plan(db) -> None:
    async with db() as session:
        session.add(
            BoardHeuristic(
                id="_draft_slot_1_plan",
                title="Draft Slot 1 Plan",
                payload=json.dumps(
                    {
                        "pick_numbers": [1, 24, 25, 48, 49],
                        "structural_note": "Picks 24 and 25 are back-to-back.",
                        "pick_1": {"take": "Bijan Robinson", "confidence": "high"},
                        "picks_24_25": {
                            "group_a_wr": ["Ja'Marr Chase"],
                            "group_b_rb_or_te": ["Sniped Guy", "Out Guy"],
                            "rule": "Take one from each group.",
                            "avoid": ["Some Other Guy"],
                        },
                    }
                ),
            )
        )
        session.add(
            BoardPlayer(name="Sniped Guy", normalized_name="sniped guy", position="RB", adp_rank=30)
        )
        session.add(
            BoardPlayer(
                name="Out Guy",
                normalized_name="out guy",
                position="RB",
                adp_rank=31,
                out_for_season=True,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_slot_plan_applicable_at_slot_one_with_live_sniped_status(client, db) -> None:
    await seed_players(db)
    await _seed_slot_plan(db)
    bijan_id = await _player_id(db, "Bijan Robinson")
    sniped_id = await _player_id(db, "Sniped Guy")

    # Bijan drafted BY ME (pick 1 -- exactly the plan's own target); Sniped Guy drafted
    # by another team (a picks_24_25 target that's now unavailable).
    await client.post(
        "/api/draft/picks",
        json={"board_player_id": bijan_id, "overall_pick": 1, "is_my_pick": True},
    )
    await client.post(
        "/api/draft/picks",
        json={
            "board_player_id": sniped_id,
            "overall_pick": 2,
            "is_my_pick": False,
            "drafted_by_team": "Rival",
        },
    )

    resp = await client.get("/api/draft/slot-plan")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["applicable"] is True  # static config's user_draft_slot is 1
    assert data["user_draft_slot"] == 1
    assert data["pick_numbers"] == [1, 24, 25, 48, 49]
    assert data["unplanned_pick_numbers"] == [48, 49]  # no pick_48/picks_48_49 block yet

    pick_1_entry = next(e for e in data["entries"] if e["picks"] == [1])
    bijan_target = pick_1_entry["targets"][0]
    assert bijan_target["name"] == "Bijan Robinson"
    assert bijan_target["drafted_by_me"] is True
    assert bijan_target["sniped"] is False
    assert bijan_target["still_available"] is False

    pair_entry = next(e for e in data["entries"] if e["picks"] == [24, 25])
    sniped_target = next(t for t in pair_entry["targets"] if t["name"] == "Sniped Guy")
    assert sniped_target["sniped"] is True
    assert sniped_target["drafted_by_team"] == "Rival"
    assert sniped_target["still_available"] is False
    chase_target = next(t for t in pair_entry["targets"] if t["name"] == "Ja'Marr Chase")
    assert chase_target["sniped"] is False
    assert chase_target["still_available"] is True

    # 6.4 fix: "still_available" is the LIVE POOL, not just "no pick recorded" -- an
    # out-for-season target (never drafted by anyone) must read as unavailable too,
    # exactly like it would if you searched for him on the real board.
    out_target = next(t for t in pair_entry["targets"] if t["name"] == "Out Guy")
    assert out_target["sniped"] is False
    assert out_target["drafted_by_me"] is False
    assert out_target["still_available"] is False


@pytest.mark.asyncio
async def test_get_slot_plan_not_applicable_off_slot_one(client, db, monkeypatch) -> None:
    """The plan's pick numbers and back-to-back reasoning are only valid at slot 1 in a
    12-team snake -- `applicable` must go False the moment the resolved league shape's
    slot isn't 1, even though the plan data itself is still returned."""
    await seed_players(db)
    await _seed_slot_plan(db)

    from backend.gridiron.services import draft_state

    real_load = draft_state._load_static_config

    def _off_slot_config():
        config = real_load()
        config["user_draft_slot"] = 4
        return config

    monkeypatch.setattr(draft_state, "_load_static_config", _off_slot_config)

    resp = await client.get("/api/draft/slot-plan")
    data = resp.json()["data"]
    assert data["applicable"] is False
    assert data["user_draft_slot"] == 4
    # Still returned, not withheld -- a UI explaining WHY it's inapplicable needs it.
    assert len(data["entries"]) == 2


# ---------------------------------------------------------------------------
# /pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pool_excludes_drafted_and_out_for_season(client, db) -> None:
    await seed_players(db)
    bijan_id = await _player_id(db, "Bijan Robinson")
    await client.post("/api/draft/picks", json={"board_player_id": bijan_id, "overall_pick": 1})

    resp = await client.get("/api/draft/pool")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["data"]["players"]}
    assert names == {"Ja'Marr Chase"}


# ---------------------------------------------------------------------------
# /state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_state_default_is_pick_one_on_the_clock(client, db) -> None:
    await seed_players(db)

    resp = await client.get("/api/draft/state")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["current_overall_pick"] == 1
    assert data["current_round"] == 1
    assert data["picks_until_next"] == 0  # slot 1 is on the clock at pick 1
    assert data["session_status"] == "manual"
    assert data["league_teams"] == STATIC_TEAMS
    assert data["draft_over"] is False
    # No kicker slot anywhere in the starter list (this league starts zero kickers).
    assert all(s["position_group"] != "K" for s in data["roster"]["starters"])
    # FLEX rendered as two distinct slots.
    flex_slots = [s["slot"] for s in data["roster"]["starters"] if s["position_group"] == "FLEX"]
    assert flex_slots == STATIC_FLEX_SLOTS


@pytest.mark.asyncio
async def test_get_state_reflects_a_recorded_pick(client, db) -> None:
    await seed_players(db)
    bijan_id = await _player_id(db, "Bijan Robinson")
    await client.post(
        "/api/draft/picks",
        json={"board_player_id": bijan_id, "overall_pick": 1, "is_my_pick": True},
    )

    resp = await client.get("/api/draft/state")
    data = resp.json()["data"]
    assert len(data["picks"]) == 1
    assert data["current_overall_pick"] == 2
    rb_slot = next(s for s in data["roster"]["starters"] if s["slot"] == "RB1")
    assert rb_slot["filled"] is True
    assert rb_slot["player"]["name"] == "Bijan Robinson"


# ---------------------------------------------------------------------------
# POST /picks, DELETE /picks/last
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pick_then_undo_restores_state_exactly(client, db) -> None:
    await seed_players(db)
    bijan_id = await _player_id(db, "Bijan Robinson")

    before = (await client.get("/api/draft/state")).json()["data"]

    resp = await client.post(
        "/api/draft/picks",
        json={"board_player_id": bijan_id, "overall_pick": 1, "is_my_pick": True},
    )
    assert resp.status_code == 201
    assert resp.json()["player_name"] == "Bijan Robinson"

    resp = await client.delete("/api/draft/picks/last")
    assert resp.status_code == 200
    assert resp.json()["undone"]["player_name"] == "Bijan Robinson"

    after = (await client.get("/api/draft/state")).json()["data"]
    assert after["picks"] == before["picks"] == []
    assert after["current_overall_pick"] == before["current_overall_pick"] == 1
    assert after["roster"] == before["roster"]


@pytest.mark.asyncio
async def test_delete_last_pick_with_no_picks_returns_none(client, db) -> None:
    resp = await client.delete("/api/draft/picks/last")
    assert resp.status_code == 200
    assert resp.json()["undone"] is None


@pytest.mark.asyncio
async def test_create_pick_conflict_returns_409(client, db) -> None:
    await client.post("/api/draft/picks", json={"player_name": "A", "overall_pick": 1})
    resp = await client.post("/api/draft/picks", json={"player_name": "B", "overall_pick": 1})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "pick_conflict"


@pytest.mark.asyncio
async def test_create_pick_missing_player_returns_400(client, db) -> None:
    resp = await client.post("/api/draft/picks", json={"overall_pick": 1})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "missing_player"


@pytest.mark.asyncio
async def test_create_pick_publishes_draft_sse_event(client, db) -> None:
    queue = events.subscribe()
    resp = await client.post("/api/draft/picks", json={"player_name": "A", "overall_pick": 1})
    assert resp.status_code == 201
    event = queue.get_nowait()
    assert event.type == "data.changed"
    assert event.scopes == ["draft"]


# ---------------------------------------------------------------------------
# PUT /current-pick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_current_pick_sets_pick_directly(client, db) -> None:
    resp = await client.put("/api/draft/current-pick", json={"overall_pick": 25})
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_overall_pick"] == 25
    assert data["current_round"] == 3  # (25-1)//12 + 1

    state = (await client.get("/api/draft/state")).json()["data"]
    assert state["current_overall_pick"] == 25


@pytest.mark.asyncio
async def test_put_current_pick_rejects_less_than_one(client, db) -> None:
    resp = await client.put("/api/draft/current-pick", json={"overall_pick": 0})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /recommendations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recommendations_returns_shortlist_with_cited_rules(client, db) -> None:
    await seed_players(db)

    resp = await client.get("/api/draft/recommendations")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["current_overall_pick"] == 1
    assert data["picks_until_next"] == 0
    assert len(data["shortlist"]) >= 1
    for rec in data["shortlist"]:
        assert rec["fired_rule_ids"]  # never empty (2.7's guarantee)
        assert set(rec["components"]) == {"value", "tier_urgency", "need", "risk", "flags"}
    assert isinstance(data["tier_alarms"], list)
    assert isinstance(data["bye_collisions"], list)
    assert isinstance(data["advisories"], list)
    assert isinstance(data["turn_pairs"], list)
    # This league starts no kicker -- the freed-bench-slot advisory should be present.
    assert any("kicker" in a.lower() for a in data["advisories"])


@pytest.mark.asyncio
async def test_get_recommendations_excludes_out_for_season_players(client, db) -> None:
    await seed_players(db)
    resp = await client.get("/api/draft/recommendations")
    names = {r["candidate"]["name"] for r in resp.json()["data"]["shortlist"]}
    assert "Hurt Guy" not in names


@pytest.mark.asyncio
async def test_get_recommendations_draft_over_returns_empty_shortlist(client, db) -> None:
    await seed_players(db)
    resp = await client.put("/api/draft/current-pick", json={"overall_pick": 170})
    assert resp.status_code == 200

    resp = await client.get("/api/draft/recommendations")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["picks_until_next"] is None
    assert data["shortlist"] == []


# ---------------------------------------------------------------------------
# GET /matches, POST /matches/{name} (task 4.5)
# ---------------------------------------------------------------------------


async def seed_matched_players(db) -> None:
    async with db() as session:
        session.add(
            BoardPlayer(
                name="Exact Guy",
                normalized_name="exact guy",
                position="RB",
                espn_player_id=101,
                match_method="exact",
                match_confidence=1.0,
            )
        )
        session.add(
            BoardPlayer(
                name="Team Changed Guy",
                normalized_name="team changed guy",
                position="WR",
                espn_player_id=102,
                match_method="team_changed",
                match_confidence=0.9,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_matches_reports_zero_below_threshold_for_a_confidently_matched_board(
    client, db
) -> None:
    """Mirrors the real committed board: 0 below the 0.9 gate. Must read as "nothing to
    resolve", not an empty/broken response -- every row is still listed."""
    await seed_matched_players(db)

    resp = await client.get("/api/draft/matches")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == CACHE_CONTROL
    data = resp.json()["data"]

    assert data["below_threshold_count"] == 0
    assert data["method_counts"] == {"exact": 1, "team_changed": 1}
    names = {m["board_player_name"]: m for m in data["matches"]}
    assert names["Exact Guy"]["espn_player_id"] == 101
    assert names["Exact Guy"]["candidates"] == []
    assert names["Team Changed Guy"]["match_confidence"] == 0.9
    assert names["Team Changed Guy"]["candidates"] == []


@pytest.mark.asyncio
async def test_get_matches_lists_low_confidence_entries_with_recovered_candidates(
    client, db, monkeypatch
) -> None:
    await seed_matched_players(db)
    async with db() as session:
        session.add(
            BoardPlayer(
                name="Amb Guy",
                normalized_name="amb guy",
                position="WR",
                match_method="unmatched",
                match_confidence=0.0,
            )
        )
        await session.commit()

    async def _stub_fetch_player_universe(year, *, http_client=None):
        return [
            EspnPlayerRef(10, "Amb Guy", "WR", "SF", False),
            EspnPlayerRef(11, "Amb Guy", "WR", "NYJ", False),
        ]

    monkeypatch.setattr(draft_matches, "fetch_player_universe", _stub_fetch_player_universe)

    resp = await client.get("/api/draft/matches")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["below_threshold_count"] == 1
    amb = next(m for m in data["matches"] if m["board_player_name"] == "Amb Guy")
    assert amb["espn_player_id"] is None
    assert {c["espn_player_id"] for c in amb["candidates"]} == {10, 11}


@pytest.mark.asyncio
async def test_post_match_override_writes_and_returns_the_updated_match(client, db) -> None:
    await seed_players(db)

    encoded_name = quote("Ja'Marr Chase")
    resp = await client.post(f"/api/draft/matches/{encoded_name}", json={"espn_player_id": 5555})
    assert resp.status_code == 200
    body = resp.json()
    assert body["board_player_name"] == "Ja'Marr Chase"
    assert body["espn_player_id"] == 5555
    assert body["match_method"] == "override"
    assert body["match_confidence"] == 1.0

    async with db() as session:
        override_row = await session.get(BoardIdOverride, "Ja'Marr Chase")
    assert override_row.espn_player_id == 5555


@pytest.mark.asyncio
async def test_post_match_override_with_null_id_records_explicit_no_match(client, db) -> None:
    await seed_players(db)

    resp = await client.post(f"/api/draft/matches/{quote('Hurt Guy')}", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["espn_player_id"] is None
    assert body["match_method"] == "override"
    assert body["match_confidence"] == 1.0


@pytest.mark.asyncio
async def test_post_match_override_unknown_name_returns_404(client, db) -> None:
    resp = await client.post(
        f"/api/draft/matches/{quote('Nobody Here')}", json={"espn_player_id": 1}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "board_player_not_found"


@pytest.mark.asyncio
async def test_match_override_survives_a_real_reimport(client, db) -> None:
    """4.5's own acceptance requirement: run the real import (real committed board,
    fixture ESPN universe -- never live network), write an override through the API for
    a real board player, re-run the import, and confirm the override survived with
    method="override"/confidence=1.0 rather than being clobbered by a fresh auto-match.
    """
    async with db() as session:
        await run_import(session, fetch_universe=_fixture_fetch_universe)

    resp = await client.post(
        f"/api/draft/matches/{quote('Puka Nacua')}", json={"espn_player_id": 999999}
    )
    assert resp.status_code == 200
    assert resp.json()["match_method"] == "override"

    # Re-import: the matcher would happily find Puka Nacua's real ESPN id -- the
    # override must still win.
    async with db() as session:
        await run_import(session, fetch_universe=_fixture_fetch_universe)

    resp = await client.get("/api/draft/matches")
    match = next(
        m for m in resp.json()["data"]["matches"] if m["board_player_name"] == "Puka Nacua"
    )
    assert match["espn_player_id"] == 999999
    assert match["match_method"] == "override"
    assert match["match_confidence"] == 1.0
