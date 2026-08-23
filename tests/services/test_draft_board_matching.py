"""Draft Assistant board <-> ESPN matching: the layered matcher (4.2), DST team-abbr
matching (4.3), and bye reconciliation (4.4) -- both the pure functions in
`backend/gridiron/services/draft_board.py` and their wiring into
`backend/gridiron/draft_board/run_import`.

Table-driven against the real fixture (`tests/fixtures/espn/draft/players_wl.json`, a real
2026 `players_wl` capture) wherever the scenario needs realistic data (DST-all-12,
precedence-fires-in-order on the real board, the aggregate match-rate report); synthetic
`EspnPlayerRef`/board-entry pairs wherever a scenario needs a specific, deterministic edge
case (ambiguity, the fuzzy threshold boundary, the same-position constraint) that would be
fragile to go hunting for in a 1027-entry fixture.

`run_import` end-to-end tests never touch the live network -- `fetch_universe` is always
injected, either returning the parsed fixture or raising to simulate an offline import.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.draft_board import run_import
from backend.gridiron.models import Base, BoardIdOverride, BoardPlayer, Player
from backend.gridiron.platforms.espn.draft import EspnPlayerRef, parse_player_universe
from backend.gridiron.services.draft_board import (
    FUZZY_RATIO_THRESHOLD,
    MatchResult,
    ByeDiscrepancy,
    load_dst_xlsx,
    load_players_json,
    match_board_players,
    normalize_name,
    reconcile_byes,
)

BOARD_DIR = Path(__file__).resolve().parents[2] / "backend" / "gridiron" / "draft_board"
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "espn"
    / "draft"
    / "players_wl.json"
)


def _ref(
    espn_player_id: int, full_name: str, position: str, nfl_team: str, is_dst: bool = False
) -> EspnPlayerRef:
    return EspnPlayerRef(
        espn_player_id=espn_player_id,
        full_name=full_name,
        position=position,
        nfl_team=nfl_team,
        is_dst=is_dst,
    )


def _entry(name: str, position: str, nfl_team: str | None = None) -> dict:
    """Minimal board-entry dict -- `match_board_players` only reads these four keys."""
    return {
        "name": name,
        "position": position,
        "nfl_team": nfl_team,
        "normalized_name": normalize_name(name),
    }


def _load_fixture_universe() -> list[EspnPlayerRef]:
    payload = json.loads(FIXTURE_PATH.read_text())
    return parse_player_universe(payload)


def _real_board_dicts() -> list[dict]:
    parsed = load_players_json(BOARD_DIR / "players.json")
    dst_rows = load_dst_xlsx(BOARD_DIR / "2026_Draft_Board.xlsx")
    return [asdict(p) for p in parsed.players] + dst_rows


# ---------------------------------------------------------------------------
# 4.2 -- precedence tiers, in order, each isolated
# ---------------------------------------------------------------------------


def test_precedence_1_override_beats_a_perfectly_matching_universe() -> None:
    universe = [_ref(501, "Bijan Robinson", "RB", "ATL")]
    board = [_entry("Bijan Robinson", "RB", "ATL")]
    results = match_board_players(board, universe, {"Bijan Robinson": 999})
    assert results == [MatchResult("Bijan Robinson", 999, "override", 1.0)]


def test_precedence_1_override_with_null_id_still_wins_and_reports_no_id() -> None:
    # A hand-maintained override can explicitly record "no real ESPN id" (e.g. a player
    # legitimately absent from the universe) -- that decision must still beat auto-matching.
    universe = [_ref(502, "Some Player", "WR", "SF")]
    board = [_entry("Some Player", "WR", "SF")]
    results = match_board_players(board, universe, {"Some Player": None})
    assert results == [MatchResult("Some Player", None, "override", 1.0)]


def test_precedence_2_exact_requires_name_position_and_team() -> None:
    universe = [_ref(101, "Puka Nacua", "WR", "LAR")]
    board = [_entry("Puka Nacua", "WR", "LAR")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Puka Nacua", 101, "exact", 1.0)]


def test_precedence_3_team_changed_fires_when_only_team_disagrees() -> None:
    # Same normalized name + position, board's team is stale (e.g. a trade after the board
    # was authored) -- ESPN's current team must not block the match.
    universe = [_ref(102, "Stefon Diggs", "WR", "NE")]
    board = [_entry("Stefon Diggs", "WR", "HOU")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Stefon Diggs", 102, "team_changed", 0.9)]


def test_precedence_4_name_only_fires_when_position_also_disagrees() -> None:
    # Name matches; both position and team disagree -- too weak for team_changed, but the
    # name itself is an exact normalized match.
    universe = [_ref(103, "Cordarrelle Patterson", "RB", "PIT")]
    board = [_entry("Cordarrelle Patterson", "WR", "PIT")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Cordarrelle Patterson", 103, "name_only", 0.8)]


def test_precedence_5_fuzzy_fires_only_when_higher_tiers_all_miss() -> None:
    close_name = "Kenneth Walkerz"
    ratio = difflib.SequenceMatcher(
        None, normalize_name("Kenneth Walker"), normalize_name(close_name)
    ).ratio()
    assert ratio >= FUZZY_RATIO_THRESHOLD  # sanity: this scenario is actually a fuzzy case

    universe = [_ref(201, close_name, "RB", "SEA")]
    board = [_entry("Kenneth Walker", "RB", "DAL")]  # team differs, name not an exact match
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Kenneth Walker", 201, "fuzzy", 0.6)]


def test_precedence_6_no_candidate_at_any_tier_is_unmatched() -> None:
    universe = [_ref(1, "Completely Different Guy", "RB", "SEA")]
    board = [_entry("Nobody Like This", "WR", "DAL")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Nobody Like This", None, "unmatched", 0.0)]


# ---------------------------------------------------------------------------
# Fuzzy: threshold boundary + same-position constraint
# ---------------------------------------------------------------------------


def test_fuzzy_respects_the_0_88_threshold_boundary() -> None:
    board_name = "Kenneth Walker"
    close_name = "Kenneth Walkerz"  # one trailing char -- expected to clear the bar
    far_name = "Ken W"  # far shorter -- expected to miss it

    ratio_close = difflib.SequenceMatcher(
        None, normalize_name(board_name), normalize_name(close_name)
    ).ratio()
    ratio_far = difflib.SequenceMatcher(
        None, normalize_name(board_name), normalize_name(far_name)
    ).ratio()
    assert ratio_close >= FUZZY_RATIO_THRESHOLD
    assert ratio_far < FUZZY_RATIO_THRESHOLD

    universe = [_ref(301, close_name, "RB", "SEA"), _ref(302, far_name, "RB", "SEA")]
    board = [_entry(board_name, "RB", "DAL")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult(board_name, 301, "fuzzy", 0.6)]


def test_fuzzy_never_crosses_position() -> None:
    close_name = "Kenneth Walkerz"
    ratio = difflib.SequenceMatcher(
        None, normalize_name("Kenneth Walker"), normalize_name(close_name)
    ).ratio()
    assert ratio >= FUZZY_RATIO_THRESHOLD  # would clear fuzzy on name alone

    universe = [_ref(303, close_name, "TE", "SEA")]  # wrong position: TE, board wants RB
    board = [_entry("Kenneth Walker", "RB", "DAL")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Kenneth Walker", None, "unmatched", 0.0)]


# ---------------------------------------------------------------------------
# Ambiguity rule -- never guess
# ---------------------------------------------------------------------------


def test_ambiguous_exact_tier_records_unmatched_with_every_candidate() -> None:
    universe = [
        _ref(401, "Michael Thomas", "WR", "NO"),
        _ref(402, "Michael Thomas", "WR", "NO"),
    ]
    board = [_entry("Michael Thomas", "WR", "NO")]
    results = match_board_players(board, universe, {})
    assert len(results) == 1
    r = results[0]
    assert r.match_method == "unmatched"
    assert r.espn_player_id is None
    assert {c.espn_player_id for c in r.candidates} == {401, 402}


def test_ambiguity_deduplicates_repeated_candidates_to_a_single_unique_match() -> None:
    # The same ESPN player id can legitimately show up twice in a lookup bucket (e.g. it
    # qualifies at exact AND would also qualify at team_changed) -- that's one real match,
    # not an ambiguity.
    universe = [_ref(401, "Michael Thomas", "WR", "NO")]
    board = [_entry("Michael Thomas", "WR", "NO")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Michael Thomas", 401, "exact", 1.0)]


# ---------------------------------------------------------------------------
# 4.3 -- DST matching by team abbreviation
# ---------------------------------------------------------------------------


def test_all_twelve_board_dsts_match_by_team() -> None:
    universe = _load_fixture_universe()
    board_dsts = load_dst_xlsx(BOARD_DIR / "2026_Draft_Board.xlsx")
    assert len(board_dsts) == 12

    results = match_board_players(board_dsts, universe, {})
    assert len(results) == 12
    for r in results:
        assert r.match_method == "exact"
        assert r.match_confidence == 1.0
        assert r.espn_player_id is not None
    assert len({r.espn_player_id for r in results}) == 12  # all distinct


def test_dst_name_based_tiers_are_never_attempted() -> None:
    # ESPN's fullName for a D/ST is the club nickname ("Falcons D/ST"), never the city, so
    # even a universe carrying a name-matchable ref must not be used for a DST board entry
    # -- only the team-abbreviation path may fire.
    universe = [_ref(-16001, "Falcons D/ST", "DST", "ATL", is_dst=True)]
    board = [{"name": "Falcons D/ST", "position": "DST", "nfl_team": None, "normalized_name": ""}]
    results = match_board_players(board, universe, {})
    # No team abbreviation resolvable from "Falcons D/ST" (it isn't in the alias table --
    # only board-style city/nickname display names are), so this must be unmatched, not a
    # name-based near-miss.
    assert results == [MatchResult("Falcons D/ST", None, "unmatched", 0.0)]


def test_dst_matches_by_team_even_though_names_never_correspond() -> None:
    universe = [_ref(-16001, "Falcons D/ST", "DST", "ATL", is_dst=True)]
    board = [_entry("Atlanta Falcons", "DST")]
    results = match_board_players(board, universe, {})
    assert results == [MatchResult("Atlanta Falcons", -16001, "exact", 1.0)]


def test_dst_ambiguous_team_hit_is_unmatched_with_candidates() -> None:
    universe = [
        _ref(-16001, "Falcons D/ST", "DST", "ATL", is_dst=True),
        _ref(-16099, "Falcons D/ST (dup)", "DST", "ATL", is_dst=True),
    ]
    board = [_entry("Atlanta Falcons", "DST")]
    results = match_board_players(board, universe, {})
    r = results[0]
    assert r.match_method == "unmatched"
    assert {c.espn_player_id for c in r.candidates} == {-16001, -16099}


def test_dst_alias_table_has_no_substring_or_prefix_fallback() -> None:
    from backend.gridiron.services.draft_board import _DST_TEAM_NAME_TO_ABBR

    # These pairs are easy to conflate with naive substring/prefix matching -- confirm the
    # lookup is exact-normalized-name-only and gets each one right.
    assert _DST_TEAM_NAME_TO_ABBR[normalize_name("LA Rams")] == "LAR"
    assert _DST_TEAM_NAME_TO_ABBR[normalize_name("LA Chargers")] == "LAC"
    assert _DST_TEAM_NAME_TO_ABBR[normalize_name("New England")] == "NE"
    assert _DST_TEAM_NAME_TO_ABBR[normalize_name("New Orleans Saints")] == "NO"
    assert normalize_name("Nowhere Team") not in _DST_TEAM_NAME_TO_ABBR


# ---------------------------------------------------------------------------
# 4.4 -- reconcile_byes (pure)
# ---------------------------------------------------------------------------


def test_reconcile_byes_detects_disagreement_and_espn_wins() -> None:
    board_entries = [{"name": "Puka Nacua", "bye": 6, "espn_player_id": 4426515}]
    discrepancies = reconcile_byes(board_entries, {4426515: 8})
    assert discrepancies == [ByeDiscrepancy("Puka Nacua", 4426515, 6, 8)]


def test_reconcile_byes_no_discrepancy_when_equal() -> None:
    board_entries = [{"name": "Puka Nacua", "bye": 6, "espn_player_id": 4426515}]
    assert reconcile_byes(board_entries, {4426515: 6}) == []


def test_reconcile_byes_skips_unmatched_and_unknown_platform_bye() -> None:
    board_entries = [
        {"name": "Unmatched Guy", "bye": 6, "espn_player_id": None},
        {"name": "No Platform Data", "bye": 6, "espn_player_id": 999},
    ]
    assert reconcile_byes(board_entries, {}) == []


# ---------------------------------------------------------------------------
# run_import wiring (4.2-4.4) -- temp DB, injected fetch_universe, never the live network
# ---------------------------------------------------------------------------


async def _session_factory(tmp_path, name: str = "draft_board_matching.db"):
    engine = make_engine(tmp_path / name)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _fixture_fetch_universe() -> list[EspnPlayerRef]:
    return _load_fixture_universe()


async def _raising_fetch_universe() -> list[EspnPlayerRef]:
    raise RuntimeError("simulated network failure")


@pytest.mark.asyncio
async def test_run_import_matches_the_real_board_against_the_fixture_universe(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            report = await run_import(session, fetch_universe=_fixture_fetch_universe)

        assert report.matching_skipped is False
        assert sum(report.match_method_counts.values()) == 161

        async with session_factory() as session:
            rows = (await session.execute(select(BoardPlayer))).scalars().all()
        assert len(rows) == 161
        assert all(r.match_method != "unmatched" and r.espn_player_id is not None for r in rows)

        dst_rows = [r for r in rows if r.position == "DST"]
        assert len(dst_rows) == 12
        assert all(r.match_method == "exact" for r in dst_rows)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_offline_leaves_everything_unmatched_without_raising(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            report = await run_import(session, fetch_universe=_raising_fetch_universe)

        assert report.matching_skipped is True

        async with session_factory() as session:
            rows = (await session.execute(select(BoardPlayer))).scalars().all()
        assert len(rows) == 161
        assert all(r.espn_player_id is None for r in rows)
        assert all(r.match_method == "unmatched" for r in rows)
        assert all(r.match_confidence == 0.0 for r in rows)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_override_beats_the_matcher_and_survives_reimport(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            session.add(BoardIdOverride(board_player_name="Jahmyr Gibbs", espn_player_id=777777))
            await session.commit()

        async with session_factory() as session:
            await run_import(session, fetch_universe=_fixture_fetch_universe)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
        assert row.espn_player_id == 777777
        assert row.match_method == "override"
        assert row.match_confidence == 1.0

        # Re-import: the matcher would happily find Gibbs' real ESPN id (4429795, exact) --
        # the override must still win.
        async with session_factory() as session:
            await run_import(session, fetch_universe=_fixture_fetch_universe)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
        assert row.espn_player_id == 777777
        assert row.match_method == "override"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_sticky_match_survives_reimport_even_offline(tmp_path) -> None:
    # A row that already has a real (non-"unmatched") match_method must not be reset to
    # unmatched just because a later import happens to run offline.
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            await run_import(session, fetch_universe=_fixture_fetch_universe)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Puka Nacua"))
            ).scalar_one()
        assert row.match_method == "exact"
        matched_id = row.espn_player_id

        async with session_factory() as session:
            await run_import(session, fetch_universe=_raising_fetch_universe)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Puka Nacua"))
            ).scalar_one()
        assert row.match_method == "exact"
        assert row.espn_player_id == matched_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_bye_reconciliation_espn_wins_and_is_reported(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        # Puka Nacua: board bye is 11 (verified against the committed xlsx/json); seed a
        # disagreeing ESPN-sourced Player row for the same id the fixture will match her to.
        async with session_factory() as session:
            session.add(
                Player(
                    id="espn:p-4426515",
                    platform="espn",
                    platform_id="4426515",
                    name="Puka Nacua",
                    position="WR",
                    nfl_team="LAR",
                    bye_week=99,
                )
            )
            await session.commit()

        async with session_factory() as session:
            report = await run_import(session, fetch_universe=_fixture_fetch_universe)

        discrepancy = next(d for d in report.bye_discrepancies if d.board_name == "Puka Nacua")
        assert discrepancy.espn_player_id == 4426515
        assert discrepancy.board_bye == 11
        assert discrepancy.platform_bye == 99

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Puka Nacua"))
            ).scalar_one()
        assert row.bye == 99  # ESPN wins
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_bye_reconciliation_no_discrepancy_when_byes_agree(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            session.add(
                Player(
                    id="espn:p-4426515",
                    platform="espn",
                    platform_id="4426515",
                    name="Puka Nacua",
                    position="WR",
                    nfl_team="LAR",
                    bye_week=11,  # matches the board's own value
                )
            )
            await session.commit()

        async with session_factory() as session:
            report = await run_import(session, fetch_universe=_fixture_fetch_universe)

        assert not any(d.board_name == "Puka Nacua" for d in report.bye_discrepancies)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Puka Nacua"))
            ).scalar_one()
        assert row.bye == 11
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Real match-rate breakdown (the human QA gate) -- reported below, not just asserted
# ---------------------------------------------------------------------------


def test_real_board_match_rate_breakdown() -> None:
    """Runs the actual layered matcher (4.2/4.3) against the real committed board and the
    real fixture universe -- no DB involved, just the pure functions -- and prints the
    per-method breakdown plus every sub-0.9-confidence entry. This is the human QA gate:
    see the test's captured output (`-s`) or the report handed back alongside this task.
    """
    universe = _load_fixture_universe()
    board = _real_board_dicts()
    results = match_board_players(board, universe, {})

    assert len(results) == len(board) == 161

    counts = Counter(r.match_method for r in results)
    low_confidence = [r for r in results if r.match_confidence < 0.9]

    print("\n--- Draft board <-> ESPN match-rate breakdown ---")
    for method, count in sorted(counts.items()):
        print(f"  {method:14s} {count:4d}")
    print(f"  {'TOTAL':14s} {len(results):4d}")
    print(f"\n--- Sub-0.9-confidence entries ({len(low_confidence)}) ---")
    for r in low_confidence:
        candidate_desc = (
            ", ".join(
                f"{c.espn_player_id}:{c.full_name}({c.position}/{c.nfl_team})" for c in r.candidates
            )
            or "-"
        )
        print(
            f"  {r.board_name:30s} {r.match_method:12s} conf={r.match_confidence:.2f}  "
            f"candidates=[{candidate_desc}]"
        )

    # Sanity floor -- catches a wholesale regression (e.g. a broken normalization) without
    # hardcoding the exact live breakdown, which can legitimately shift as rosters move.
    assert counts["exact"] + counts["team_changed"] >= 150
    assert counts["unmatched"] <= 5
