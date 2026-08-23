"""Draft Assistant board import: `normalize_name`, the players.json / DST xlsx / strategy
rules parsers (`backend/gridiron/services/draft_board.py`), and the end-to-end idempotent
import (`backend/gridiron/draft_board`)."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.draft_board import run_import
from backend.gridiron.models import Base, BoardPlayer
from backend.gridiron.services.draft_board import (
    load_dst_xlsx,
    load_players_json,
    load_strategy_rules,
    normalize_name,
    parse_take_in_round,
)

BOARD_DIR = Path(__file__).resolve().parents[2] / "backend" / "gridiron" / "draft_board"


# ---------------------------------------------------------------------------
# 1.3 normalize_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Ja'Marr Chase", "jamarr chase"),
        ("De'Von Achane", "devon achane"),
        ("D'Andre Swift", "dandre swift"),
        ("Jaxon Smith-Njigba", "jaxon smith njigba"),
        ("Amon-Ra St. Brown", "amon ra st brown"),
        ("A.J. Brown", "a j brown"),
        ("Travis Etienne Jr.", "travis etienne"),
        ("Kenneth Walker III", "kenneth walker"),
        ("Kyle Pitts Sr.", "kyle pitts"),
        ("James Cook III", "james cook"),
        ("Deebo Samuel Sr.", "deebo samuel"),
        # Not present in players.json, but the suffix-token mechanism must handle IV too.
        ("Robert Griffin IV", "robert griffin"),
        # No accented name exists in the source data; this exercises the NFKD fold itself.
        ("José Ramírez", "jose ramirez"),
        # Idempotent / whitespace-insensitive.
        ("  Bijan   Robinson  ", "bijan robinson"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_normalize_name_all_players_json_names_are_unique_source_names() -> None:
    # Sanity check on the underlying assumption the whole import relies on: the upsert
    # conflict target is `name`, so real names in the source file must be unique.
    data = json.loads((BOARD_DIR / "players.json").read_text())
    names = [rec["name"] for rec in data]
    assert len(names) == len(set(names)) == 149


# ---------------------------------------------------------------------------
# take_in_round parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Rd 4", (4, 4)),
        ("Rd 2-3", (2, 3)),
        ("Rd 9-10", (9, 10)),
        (None, None),
        ("", None),
        ("garbage", None),
    ],
)
def test_parse_take_in_round(raw, expected) -> None:
    assert parse_take_in_round(raw) == expected


# ---------------------------------------------------------------------------
# 1.4 load_players_json
# ---------------------------------------------------------------------------


def test_load_players_json_parses_all_records() -> None:
    parsed = load_players_json(BOARD_DIR / "players.json")
    assert len(parsed.players) == 149


def test_load_players_json_null_adp_players_have_no_exception_and_null_fields() -> None:
    parsed = load_players_json(BOARD_DIR / "players.json")
    null_adp = {p.name: p for p in parsed.players if p.adp is None}
    assert set(null_adp) == {"Ricky Pearsall", "Tyreek Hill", "Chris Brazzell", "Kenyon Sadiq"}
    for p in null_adp.values():
        assert p.adp_rank is None
        assert p.adp_round is None
        assert p.adp_pick is None


def test_load_players_json_deduped_tiers() -> None:
    parsed = load_players_json(BOARD_DIR / "players.json")
    overall = [t for t in parsed.tiers if t.scope == "overall"]
    positional = [t for t in parsed.tiers if t.scope == "positional"]
    assert {t.tier for t in overall} == set(range(1, 9))
    assert all(t.position is None for t in overall)
    # No duplicate (scope, position, tier) keys.
    keys = [(t.scope, t.position, t.tier) for t in parsed.tiers]
    assert len(keys) == len(set(keys))
    assert len(positional) > 0


def test_load_players_json_first_occurrence_wins_on_inconsistent_labels() -> None:
    # Known source-data defect: QB tier 4's positional_tier_label disagrees between
    # records. Jared Goff appears before the other QB-tier-4 players in players.json and
    # carries "NEUTRAL-TO-AVOID"; confirm the deterministic first-wins tie-break.
    data = json.loads((BOARD_DIR / "players.json").read_text())
    qb4_labels = [
        rec["positional_tier_label"]
        for rec in data
        if rec.get("position") == "QB" and rec.get("positional_tier") == 4
    ]
    assert len(set(qb4_labels)) > 1  # confirms the defect still exists in the source file

    parsed = load_players_json(BOARD_DIR / "players.json")
    row = next(
        t for t in parsed.tiers if t.scope == "positional" and t.position == "QB" and t.tier == 4
    )
    assert row.label == qb4_labels[0]


def test_load_players_json_flags_are_json_encoded() -> None:
    parsed = load_players_json(BOARD_DIR / "players.json")
    gibbs = next(p for p in parsed.players if p.name == "Jahmyr Gibbs")
    assert json.loads(gibbs.flags) == []
    assert json.loads(gibbs.injury_tags) == ["mcl"]

    rice = next(p for p in parsed.players if p.name == "Rashee Rice")
    assert json.loads(rice.flags) == ["NEUTRAL"]
    takes = json.loads(rice.analyst_takes)
    assert takes[0]["source"] == "The Fantasy Footballers"


def test_load_players_json_unpriced_risk_default_sibling_file() -> None:
    # Single-arg call must pick up the real unpriced_risk.json sitting next to players.json.
    parsed = load_players_json(BOARD_DIR / "players.json")
    love = next(p for p in parsed.players if p.name == "Jeremiyah Love")
    pierce = next(p for p in parsed.players if p.name == "Alec Pierce")
    assert love.unpriced_risk is True
    assert pierce.unpriced_risk is True
    # A player absent from unpriced_risk.json's map must default to False.
    gibbs = next(p for p in parsed.players if p.name == "Jahmyr Gibbs")
    assert gibbs.unpriced_risk is False


def test_load_players_json_unpriced_risk_explicit_path_override(tmp_path) -> None:
    override_path = tmp_path / "custom_unpriced_risk.json"
    override_path.write_text(json.dumps({"unpriced_risk": {"Jahmyr Gibbs": True}}))
    parsed = load_players_json(BOARD_DIR / "players.json", unpriced_risk_path=override_path)
    gibbs = next(p for p in parsed.players if p.name == "Jahmyr Gibbs")
    assert gibbs.unpriced_risk is True
    love = next(p for p in parsed.players if p.name == "Jeremiyah Love")
    assert love.unpriced_risk is False


# ---------------------------------------------------------------------------
# 1.5 load_dst_xlsx
# ---------------------------------------------------------------------------


def test_load_dst_xlsx_returns_exactly_twelve_rows() -> None:
    rows = load_dst_xlsx(BOARD_DIR / "2026_Draft_Board.xlsx")
    assert len(rows) == 12
    assert all(r["position"] == "DST" for r in rows)
    assert all(r["overall_tier"] is None and r["positional_tier"] is None for r in rows)


def test_load_dst_xlsx_spot_check_seattle() -> None:
    rows = load_dst_xlsx(BOARD_DIR / "2026_Draft_Board.xlsx")
    seattle = next(r for r in rows if r["name"] == "Seattle Seahawks")
    assert seattle["bye"] == 11
    assert seattle["adp"] == pytest.approx(82.9, abs=0.01)
    assert seattle["adp_round"] == 7
    assert seattle["adp_pick"] == 11
    assert seattle["take_in_round"] == "7.11"
    assert seattle["risk"] == "Low-Med"
    assert "Super Bowl champs" in seattle["note"]
    assert seattle["normalized_name"] == normalize_name("Seattle Seahawks")


def test_load_dst_xlsx_note_can_be_empty() -> None:
    rows = load_dst_xlsx(BOARD_DIR / "2026_Draft_Board.xlsx")
    rams = next(r for r in rows if r["name"] == "LA Rams")
    assert rams["note"] is None


# ---------------------------------------------------------------------------
# 1.6 load_strategy_rules
# ---------------------------------------------------------------------------


def test_load_strategy_rules_covers_all_heuristics_and_synthetic_blocks() -> None:
    rows = load_strategy_rules(BOARD_DIR / "strategy_rules.json")
    ids = {r["id"] for r in rows}
    expected_heuristics = {
        "draft_the_tier",
        "flex_pressure",
        "no_kicker",
        "elite_te_window",
        "qb_wait",
        "dst_last",
        "handcuff_own_studs",
        "bye_stacking",
        "injury_discount",
    }
    assert expected_heuristics <= ids
    assert {"_positional_cliffs", "_value_calc", "_draft_slot_1_plan"} <= ids
    assert len(rows) == len(expected_heuristics) + 3


def test_load_strategy_rules_payload_is_full_source_object() -> None:
    rows = load_strategy_rules(BOARD_DIR / "strategy_rules.json")
    injury_discount = next(r for r in rows if r["id"] == "injury_discount")
    payload = json.loads(injury_discount["payload"])
    assert payload["id"] == "injury_discount"
    assert "Jeremiyah Love" in payload["rule"]

    value_calc = next(r for r in rows if r["id"] == "_value_calc")
    payload = json.loads(value_calc["payload"])
    assert "adp_delta" in payload


# ---------------------------------------------------------------------------
# 1.7 / 1.7b / 1.8 -- run_import end-to-end
# ---------------------------------------------------------------------------


async def _session_factory(tmp_path):
    engine = make_engine(tmp_path / "draft_board_import.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.mark.asyncio
async def test_run_import_acceptance_counts(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            report = await run_import(session)

        assert report.board_players_total == 161

        async with session_factory() as session:
            rows = (await session.execute(select(BoardPlayer))).scalars().all()
            target = sum(1 for r in rows if "TARGET" in json.loads(r.flags or "[]"))
            fade = sum(1 for r in rows if "FADE" in json.loads(r.flags or "[]"))
            sleeper = sum(1 for r in rows if "SLEEPER" in json.loads(r.flags or "[]"))
            rookies = sum(1 for r in rows if r.rookie)
            dst_count = sum(1 for r in rows if r.position == "DST")

            assert target == 22
            assert fade == 7
            assert sleeper == 25
            assert rookies == 11
            assert dst_count == 12
            assert len(rows) == 161
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_1_7b_flag_omission_defects_reported(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            report = await run_import(session)
        assert "Jeremiyah Love" in report.flag_omission_defects
        assert "Alec Pierce" in report.flag_omission_defects
        # every reported name really does have risk_score >= 4 and empty flags
        async with session_factory() as session:
            rows = (await session.execute(select(BoardPlayer))).scalars().all()
        by_name = {r.name: r for r in rows}
        for name in report.flag_omission_defects:
            row = by_name[name]
            assert row.risk_score is not None and row.risk_score >= 4
            assert json.loads(row.flags or "[]") == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_is_idempotent(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            await run_import(session)

        async def dump():
            async with session_factory() as session:
                players = (
                    await session.execute(
                        text(
                            "select id,name,normalized_name,position,nfl_team,bye,adp,adp_rank,"
                            "adp_round,adp_pick,overall_tier,positional_tier,risk,risk_score,"
                            "rookie,out_for_season,unpriced_risk,note,thesis,take_in_round,"
                            "sleeper_category,catalyst,format_fit,flags,injury_tags,"
                            "analyst_takes,sources,espn_player_id,match_method,match_confidence "
                            "from board_players order by id"
                        )
                    )
                ).fetchall()
                tiers = (
                    await session.execute(
                        text(
                            "select scope,position,tier,label from board_tiers order by scope,position,tier"
                        )
                    )
                ).fetchall()
                heuristics = (
                    await session.execute(
                        text("select id,title,body,payload from board_heuristics order by id")
                    )
                ).fetchall()
                return players, tiers, heuristics

        before = await dump()

        async with session_factory() as session:
            await run_import(session)

        after = await dump()

        assert before == after
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_preserves_espn_match_fields_across_reimport(tmp_path) -> None:
    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            await run_import(session)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
            row.espn_player_id = 4429795
            row.match_method = "exact"
            row.match_confidence = 0.97
            await session.commit()

        async with session_factory() as session:
            await run_import(session)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
            assert row.espn_player_id == 4429795
            assert row.match_method == "exact"
            assert row.match_confidence == 0.97
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_import_override_wins_over_existing_match(tmp_path) -> None:
    from backend.gridiron.models import BoardIdOverride

    session_factory, engine = await _session_factory(tmp_path)
    try:
        async with session_factory() as session:
            await run_import(session)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
            row.espn_player_id = 111
            row.match_method = "fuzzy"
            row.match_confidence = 0.5
            session.add(BoardIdOverride(board_player_name="Jahmyr Gibbs", espn_player_id=999999))
            await session.commit()

        async with session_factory() as session:
            await run_import(session)

        async with session_factory() as session:
            row = (
                await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Jahmyr Gibbs"))
            ).scalar_one()
            assert row.espn_player_id == 999999
            assert row.match_method == "override"
    finally:
        await engine.dispose()
