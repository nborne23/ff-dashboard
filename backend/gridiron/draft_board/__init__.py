"""Draft Assistant board source data + idempotent DB import.

The data files here (`players.json`, `strategy_rules.json`, `2026_Draft_Board.xlsx`,
`unpriced_risk.json`) are committed, read-only inputs. `run_import` is the orchestration
layer: it calls the pure parsers in `backend/gridiron/services/draft_board.py`, then
upserts the results into `board_players` / `board_tiers` / `board_heuristics`. Run it via
`python -m backend.gridiron.draft_board import`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import BoardHeuristic, BoardIdOverride, BoardPlayer, BoardTier, Player
from backend.gridiron.platforms.espn.draft import (
    PLAYERS_WL_BASE,
    EspnPlayerRef,
    fetch_player_universe,
)
from backend.gridiron.services.draft_board import (
    ByeDiscrepancy,
    MatchResult,
    load_dst_xlsx,
    load_players_json,
    load_strategy_rules,
    match_board_players,
    reconcile_byes,
)

PACKAGE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger(__name__)

_DEFAULT_SEASON = 2026


def _default_espn_year() -> int:
    """Read the season year out of the board's own `league_config.json` (falling back to
    `_DEFAULT_SEASON` if the file is missing/malformed) so the matcher targets the same
    season the board itself was drafted for, without hardcoding it at the call site."""
    try:
        data = json.loads((PACKAGE_DIR / "league_config.json").read_text())
        return int(data["season"])
    except Exception:
        return _DEFAULT_SEASON


# Columns re-derived from source data on every import. Deliberately excludes
# espn_player_id / match_method / match_confidence -- those belong to a later matching
# phase and must survive re-import untouched (see `_apply_player_fields`).
_PLAYER_FIELDS = (
    "normalized_name",
    "position",
    "nfl_team",
    "bye",
    "adp",
    "adp_rank",
    "adp_round",
    "adp_pick",
    "overall_tier",
    "positional_tier",
    "risk",
    "risk_score",
    "rookie",
    "out_for_season",
    "unpriced_risk",
    "note",
    "thesis",
    "take_in_round",
    "sleeper_category",
    "catalyst",
    "format_fit",
    "flags",
    "injury_tags",
    "analyst_takes",
    "sources",
)


@dataclass(frozen=True)
class ImportReport:
    """Summary of one `run_import` call, printed by the CLI.

    The 4.2-4.4 fields all default so existing callers (and the CLI) that only read the
    original fields keep working unchanged:

    - `matching_skipped`: True when the ESPN player universe couldn't be fetched this run
      (network/DNS/HTTP failure) -- every board player without an override was imported
      with `espn_player_id=None`/`match_method="unmatched"` rather than failing the import.
    - `match_method_counts`: this run's fresh matcher output (not the DB's final sticky
      state -- see `run_import`'s docstring), one count per `match_method` value seen.
    - `low_confidence_matches`: every `MatchResult` this run with `match_confidence < 0.9`
      (i.e. everything except `override`/`exact`), candidates included -- the human QA gate.
    - `bye_discrepancies`: every board/platform bye disagreement detected this run, already
      resolved in the DB (ESPN's value wins) by the time this report is returned.
    """

    players_seen: int
    board_players_total: int
    tiers_seen: int
    heuristics_seen: int
    flag_omission_defects: tuple[str, ...]
    matching_skipped: bool = False
    match_method_counts: dict[str, int] = field(default_factory=dict)
    low_confidence_matches: tuple[MatchResult, ...] = field(default_factory=tuple)
    bye_discrepancies: tuple[ByeDiscrepancy, ...] = field(default_factory=tuple)


def _apply_player_fields(row: BoardPlayer, fields: dict) -> None:
    for name in _PLAYER_FIELDS:
        setattr(row, name, fields[name])


def _flag_omission_defects(all_player_dicts: list[dict]) -> list[str]:
    """Players with risk_score >= 4 but an EMPTY `flags` array -- known defect in the
    board export (task 1.7b): it drops FADE for at least Jeremiyah Love and Alec Pierce,
    whose own note prose reads "ADP has actually RISEN... Let someone else pay" and "Hard
    fade" respectively. Only the source export can fix this; the report just surfaces it.
    """
    defects = []
    for fields in all_player_dicts:
        risk_score = fields.get("risk_score")
        if risk_score is None or risk_score < 4:
            continue
        flags = json.loads(fields.get("flags") or "[]")
        if not flags:
            defects.append(fields["name"])
    return sorted(defects)


async def _default_fetch_universe(year: int) -> list[EspnPlayerRef]:
    """Default `fetch_universe` for `run_import`: a short-timeout client so a
    blackholed/unreachable network fails fast (seconds, not `fetch_player_universe`'s own
    30s default) rather than stalling every import attempt."""
    async with httpx.AsyncClient(base_url=PLAYERS_WL_BASE, timeout=10) as client:
        return await fetch_player_universe(year, http_client=client)


async def run_import(
    session: AsyncSession,
    *,
    players_json_path: str | Path | None = None,
    dst_xlsx_path: str | Path | None = None,
    strategy_rules_path: str | Path | None = None,
    unpriced_risk_path: str | Path | None = None,
    espn_year: int | None = None,
    fetch_universe: Callable[[], Awaitable[list[EspnPlayerRef]]] | None = None,
) -> ImportReport:
    """Idempotently upsert the board source data into the DB via `session`, then match it
    against the ESPN player universe (4.2/4.3) and reconcile bye weeks against ESPN's own
    `players` table (4.4).

    Upsert conflict targets: `board_players.name`, `board_tiers(scope, position, tier)`,
    `board_heuristics.id`. `board_id_overrides` is only ever READ here (never written --
    it's hand-maintained).

    Matching is **sticky**: a board player keeps its current `espn_player_id` /
    `match_method` / `match_confidence` across re-imports once it has ANY non-"unmatched"
    method -- whether that came from a prior successful auto-match or a hand-edited DB
    row -- so re-running the import never regresses a good match to a worse one just
    because the matcher's live inputs shifted. The one exception is `board_id_overrides`:
    an override is re-applied on every import regardless of the row's current state,
    because it's hand-maintained precisely to correct a bad match. A brand-new row (or one
    still stuck at `"unmatched"`) is always retried, since ESPN's player universe can gain
    a player between imports.

    `fetch_universe` (year -> universe, zero-arg) defaults to `_default_fetch_universe`
    fetching live from ESPN for `espn_year` (defaulting to the board's own
    `league_config.json` season). If it raises for any reason (network down, ESPN
    unreachable, bad payload), the import still succeeds: every board player without an
    override gets `espn_player_id=None`/`match_method="unmatched"`, and
    `ImportReport.matching_skipped` is set so the caller can tell offline import apart from
    "the matcher genuinely found nothing."
    """
    players_json_path = players_json_path or PACKAGE_DIR / "players.json"
    dst_xlsx_path = dst_xlsx_path or PACKAGE_DIR / "2026_Draft_Board.xlsx"
    strategy_rules_path = strategy_rules_path or PACKAGE_DIR / "strategy_rules.json"
    unpriced_risk_path = unpriced_risk_path or PACKAGE_DIR / "unpriced_risk.json"

    parsed = load_players_json(players_json_path, unpriced_risk_path=unpriced_risk_path)
    dst_rows = load_dst_xlsx(dst_xlsx_path)
    heuristic_rows = load_strategy_rules(strategy_rules_path)

    all_player_dicts = [asdict(p) for p in parsed.players] + dst_rows
    flag_defects = _flag_omission_defects(all_player_dicts)

    overrides_result = await session.execute(select(BoardIdOverride))
    overrides_by_name = {row.board_player_name: row for row in overrides_result.scalars().all()}
    overrides_map: dict[str, int | None] = {
        name: row.espn_player_id for name, row in overrides_by_name.items()
    }

    existing_result = await session.execute(select(BoardPlayer))
    existing_players_by_name = {row.name: row for row in existing_result.scalars().all()}

    try:
        if fetch_universe is not None:
            universe = await fetch_universe()
        else:
            universe = await _default_fetch_universe(espn_year or _default_espn_year())
        matching_skipped = False
    except Exception:
        logger.warning(
            "ESPN player universe fetch failed -- importing board with matching skipped",
            exc_info=True,
        )
        universe = []
        matching_skipped = True

    match_results = match_board_players(all_player_dicts, universe, overrides_map)
    match_results_by_name = {r.board_name: r for r in match_results}

    for fields in all_player_dicts:
        name = fields["name"]
        row = existing_players_by_name.get(name)
        if row is None:
            row = BoardPlayer(
                name=name, espn_player_id=None, match_method="unmatched", match_confidence=0.0
            )
            session.add(row)
            existing_players_by_name[name] = row
        _apply_player_fields(row, fields)

        result = match_results_by_name[name]
        if result.match_method == "override" or row.match_method in (None, "unmatched"):
            row.espn_player_id = result.espn_player_id
            row.match_method = result.match_method
            row.match_confidence = result.match_confidence
        # else: this row already carries a sticky non-"unmatched" match (auto or
        # hand-edited) and there's no override for it -- leave it exactly as it was.

    # 4.4 -- bye reconciliation. Board byes must be read here (post `_apply_player_fields`,
    # pre platform-overwrite below) so a second run against unchanged inputs reports the
    # same discrepancies rather than comparing ESPN's own value against itself.
    espn_ids = [
        row.espn_player_id
        for row in existing_players_by_name.values()
        if row.espn_player_id is not None
    ]
    platform_byes: dict[int, int | None] = {}
    if espn_ids:
        platform_rows = await session.execute(
            select(Player.platform_id, Player.bye_week).where(
                Player.platform == "espn",
                Player.platform_id.in_([str(i) for i in espn_ids]),
            )
        )
        platform_byes = {int(pid): bye for pid, bye in platform_rows.all()}

    board_entries_for_bye = [
        {"name": row.name, "bye": row.bye, "espn_player_id": row.espn_player_id}
        for row in existing_players_by_name.values()
    ]
    bye_discrepancies = reconcile_byes(board_entries_for_bye, platform_byes)
    for d in bye_discrepancies:
        logger.warning(
            "Bye week discrepancy for %s (espn_player_id=%s): board=%s platform=%s -- "
            "platform (ESPN) wins",
            d.board_name,
            d.espn_player_id,
            d.board_bye,
            d.platform_bye,
        )

    for row in existing_players_by_name.values():
        if row.espn_player_id is None:
            continue
        platform_bye = platform_byes.get(row.espn_player_id)
        if platform_bye is not None:
            row.bye = platform_bye

    tiers_result = await session.execute(select(BoardTier))
    existing_tiers = {(t.scope, t.position, t.tier): t for t in tiers_result.scalars().all()}
    for t in parsed.tiers:
        key = (t.scope, t.position, t.tier)
        row = existing_tiers.get(key)
        if row is None:
            session.add(BoardTier(scope=t.scope, position=t.position, tier=t.tier, label=t.label))
        else:
            row.label = t.label

    heuristics_result = await session.execute(select(BoardHeuristic))
    existing_heuristics = {h.id: h for h in heuristics_result.scalars().all()}
    for h in heuristic_rows:
        row = existing_heuristics.get(h["id"])
        if row is None:
            row = BoardHeuristic(id=h["id"])
            session.add(row)
        row.title = h["title"]
        row.body = h["body"]
        row.payload = h["payload"]

    await session.commit()

    total = await session.scalar(select(func.count()).select_from(BoardPlayer))

    match_method_counts: dict[str, int] = {}
    for r in match_results:
        match_method_counts[r.match_method] = match_method_counts.get(r.match_method, 0) + 1
    low_confidence_matches = tuple(r for r in match_results if r.match_confidence < 0.9)

    return ImportReport(
        players_seen=len(all_player_dicts),
        board_players_total=total or 0,
        tiers_seen=len(parsed.tiers),
        heuristics_seen=len(heuristic_rows),
        flag_omission_defects=tuple(flag_defects),
        matching_skipped=matching_skipped,
        match_method_counts=match_method_counts,
        low_confidence_matches=low_confidence_matches,
        bye_discrepancies=tuple(bye_discrepancies),
    )
