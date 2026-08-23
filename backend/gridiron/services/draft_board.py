"""Pure parsers for the Draft Assistant board source data (`backend/gridiron/draft_board/`).

Nothing in this module touches a database or the network -- it only reads the committed
JSON/XLSX files and returns plain dataclasses/dicts ready for upsert by
`backend/gridiron/draft_board/__init__.py`.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from backend.gridiron.platforms.espn.draft import EspnPlayerRef

# ---------------------------------------------------------------------------
# 1.3 -- name normalization
# ---------------------------------------------------------------------------

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_PUNCT_TO_SPACE_RE = re.compile(r"[-.]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Fold a player name into a stable matching key.

    Steps, in order: NFKD-fold and drop combining marks (de-accent); lowercase; drop a
    trailing generational suffix (Jr/Sr/II/III/IV, with or without a period) as a whole
    token; drop apostrophes outright (`Ja'Marr` -> `jamarr`, matching how the name is
    said/typed without one); turn hyphens and periods into spaces (`Smith-Njigba` ->
    `smith njigba`, `A.J.` -> `a j`) so multi-part names still tokenize; collapse
    whitespace and strip. Punctuation handling is deliberately asymmetric (apostrophes
    vanish, hyphens/periods become spaces) because an apostrophe never separates two real
    tokens in these names while a hyphen or period-abbreviated initial does.
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    lowered = folded.lower()

    tokens = lowered.split()
    if tokens and tokens[-1].rstrip(".") in _SUFFIXES:
        tokens = tokens[:-1]
    joined = " ".join(tokens)

    joined = joined.replace("'", "")
    joined = _PUNCT_TO_SPACE_RE.sub(" ", joined)
    joined = _WHITESPACE_RE.sub(" ", joined).strip()
    return joined


# ---------------------------------------------------------------------------
# 1.4 -- players.json
# ---------------------------------------------------------------------------

_TAKE_IN_ROUND_RE = re.compile(r"Rd\s*(\d+)(?:\s*-\s*(\d+))?", re.IGNORECASE)


def parse_take_in_round(raw: str | None) -> tuple[int, int] | None:
    """Range-tolerant parse of the display-only `take_in_round` string.

    Handles both `"Rd 4"` (returns `(4, 4)`) and `"Rd 2-3"` / `"Rd 9-10"` (returns the
    low/high pair). Never raises -- unparseable or missing input returns `None`. Nothing
    in scoring reads this; it exists only so callers don't have to hand-roll the regex.
    """
    if not raw:
        return None
    match = _TAKE_IN_ROUND_RE.search(raw)
    if not match:
        return None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else low
    return (low, high)


@dataclass(frozen=True)
class ParsedPlayer:
    """One board player, field-for-field ready to become (or update) a `BoardPlayer` row.
    `flags`/`injury_tags`/`analyst_takes`/`sources` are already `json.dumps`-encoded."""

    name: str
    normalized_name: str
    position: str
    nfl_team: str | None
    bye: int | None
    adp: float | None
    adp_rank: int | None
    adp_round: int | None
    adp_pick: int | None
    overall_tier: int | None
    positional_tier: int | None
    risk: str | None
    risk_score: int | None
    rookie: bool
    out_for_season: bool
    unpriced_risk: bool
    note: str | None
    thesis: str | None
    take_in_round: str | None
    sleeper_category: str | None
    catalyst: str | None
    format_fit: str | None
    flags: str
    injury_tags: str
    analyst_takes: str
    sources: str


@dataclass(frozen=True)
class ParsedTier:
    """One deduped `board_tiers` row."""

    scope: str
    position: str | None
    tier: int
    label: str


@dataclass(frozen=True)
class ParsedBoard:
    players: list[ParsedPlayer]
    tiers: list[ParsedTier]


def load_players_json(
    path: str | Path, unpriced_risk_path: str | Path | None = None
) -> ParsedBoard:
    """Parse `players.json` into upsert-ready players plus deduped tier rows.

    `unpriced_risk_path` defaults to `unpriced_risk.json` next to `path` (the layout the
    source data actually ships in); pass an explicit path (or a nonexistent one) to
    override. Names absent from the unpriced-risk map default to `False`, per its own
    `_comment`.

    Tier dedup is first-occurrence-wins per `(scope, position, tier)`, keyed on the JSON
    list's own (stable) order -- so re-running against the same file is deterministic and
    idempotent. This matters because the source data is NOT internally consistent: 3 of
    149 records carry a `positional_tier_label` that disagrees with every other member of
    their tier (QB tier 4 / Jared Goff, WR tier 7 / Jerry Jeudy & De'Zhaun Stribling) --
    a real defect in the export, not a bug here.
    """
    path = Path(path)
    data = json.loads(path.read_text())

    if unpriced_risk_path is None:
        candidate = path.parent / "unpriced_risk.json"
        unpriced_risk_path = candidate if candidate.exists() else None

    unpriced_map: dict[str, bool] = {}
    if unpriced_risk_path is not None and Path(unpriced_risk_path).exists():
        raw = json.loads(Path(unpriced_risk_path).read_text())
        unpriced_map = raw.get("unpriced_risk", {})

    # `out_for_season` in the export is keyword-derived from note prose, the same defect
    # class as `injury_tags` -- and it is far more consequential, because it removes a
    # player from the draftable pool entirely. Nico Collins (HOU WR1, ADP 21.5) was
    # flagged out because his note describes *Jayden Higgins* tearing an ACL. The
    # curated file next to the board overrides the export per player.
    out_for_season_map: dict[str, bool] = {}
    corrections = path.parent / "out_for_season.json"
    if corrections.exists():
        out_for_season_map = json.loads(corrections.read_text()).get("out_for_season", {})

    players: list[ParsedPlayer] = []
    tier_rows: dict[tuple[str, str | None, int], ParsedTier] = {}

    for rec in data:
        name = rec["name"]
        position = rec.get("position")
        overall_tier = rec.get("overall_tier")
        positional_tier = rec.get("positional_tier")

        tier_label = rec.get("tier_label")
        if overall_tier is not None and tier_label:
            key = ("overall", None, overall_tier)
            tier_rows.setdefault(key, ParsedTier("overall", None, overall_tier, tier_label))

        positional_tier_label = rec.get("positional_tier_label")
        if positional_tier is not None and positional_tier_label:
            key = ("positional", position, positional_tier)
            tier_rows.setdefault(
                key, ParsedTier("positional", position, positional_tier, positional_tier_label)
            )

        players.append(
            ParsedPlayer(
                name=name,
                normalized_name=normalize_name(name),
                position=position,
                nfl_team=rec.get("team"),
                bye=rec.get("bye"),
                adp=rec.get("adp"),
                adp_rank=rec.get("adp_rank"),
                adp_round=rec.get("adp_round"),
                adp_pick=rec.get("adp_pick"),
                overall_tier=overall_tier,
                positional_tier=positional_tier,
                risk=rec.get("risk"),
                risk_score=rec.get("risk_score"),
                rookie=bool(rec.get("rookie", False)),
                out_for_season=bool(out_for_season_map.get(name, rec.get("out_for_season", False))),
                unpriced_risk=bool(unpriced_map.get(name, False)),
                note=rec.get("note"),
                thesis=rec.get("thesis"),
                take_in_round=rec.get("take_in_round"),
                sleeper_category=rec.get("sleeper_category"),
                catalyst=rec.get("catalyst"),
                format_fit=rec.get("format_fit"),
                flags=json.dumps(rec.get("flags") or []),
                injury_tags=json.dumps(rec.get("injury_tags") or []),
                analyst_takes=json.dumps(rec.get("analyst_takes") or []),
                sources=json.dumps(rec.get("sources") or []),
            )
        )

    return ParsedBoard(players=players, tiers=list(tier_rows.values()))


# ---------------------------------------------------------------------------
# 1.5 -- DST xlsx (stdlib zipfile + ElementTree only)
# ---------------------------------------------------------------------------

_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col_letters(cell_ref: str) -> str:
    return "".join(ch for ch in cell_ref if ch.isalpha())


def _load_shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    strings = []
    for si in root.findall(f"{_MAIN_NS}si"):
        strings.append("".join(t.text or "" for t in si.iter(f"{_MAIN_NS}t")))
    return strings


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str | float | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        is_el = cell.find(f"{_MAIN_NS}is")
        if is_el is None:
            return None
        return "".join(t.text or "" for t in is_el.iter(f"{_MAIN_NS}t"))

    v_el = cell.find(f"{_MAIN_NS}v")
    if v_el is None or v_el.text is None:
        return None

    if cell_type == "s":
        idx = int(v_el.text)
        return shared_strings[idx] if idx < len(shared_strings) else None

    if cell_type == "str":
        return v_el.text

    try:
        return float(v_el.text)
    except ValueError:
        return v_el.text


def _find_sheet_path_by_name(z: zipfile.ZipFile, sheet_name: str) -> str:
    """Resolve a worksheet name to its part path via workbook.xml + workbook.xml.rels --
    never hardcode a `sheetN.xml` filename, sheet order in the zip is not guaranteed to
    match the tab order."""
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rid = None
    for sheet in workbook.iter(f"{_MAIN_NS}sheet"):
        if sheet.get("name") == sheet_name:
            rid = sheet.get(f"{_R_NS}id")
            break
    if rid is None:
        raise ValueError(f"No sheet named {sheet_name!r} found in xl/workbook.xml")

    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f"{_PKG_REL_NS}Relationship"):
        if rel.get("Id") == rid:
            target = rel.get("Target") or ""
            return target[1:] if target.startswith("/") else f"xl/{target}"
    raise ValueError(f"No relationship found for r:id {rid!r}")


def load_dst_xlsx(path: str | Path) -> list[dict]:
    """Parse the `DST` sheet of `2026_Draft_Board.xlsx` into 12 board-player-shaped dicts.

    The sheet layout (verified against the actual file, not assumed): row 1 is the
    header; row 2 is a single merged commentary cell; rows 3-14 are the 12 defenses; row
    15 is a single merged "STRATEGY" section header; row 16 is a "How to play it" note
    row (its Bye/ADP/etc. cells hold literal `"-"` strings, not numbers). Rather than
    hardcode row numbers, a row is treated as real defense data only when its `Bye` cell
    (column B) is present and numeric -- which is true of exactly the 12 defense rows and
    false of every header/commentary/strategy row, so this is robust to the sheet
    growing/shrinking commentary rows around the data.

    `Rd.Pk` (e.g. `"7.11"`, `"12.10"`) is stored both as the raw string in
    `take_in_round` (for display, matching players.json's own field) and split on `.`
    into `adp_round`/`adp_pick` ints, so DST rows are queryable the same way skill
    players are.
    """
    with zipfile.ZipFile(path) as z:
        sheet_path = _find_sheet_path_by_name(z, "DST")
        shared_strings = _load_shared_strings(z)
        root = ET.fromstring(z.read(sheet_path))

        results: list[dict] = []
        for row in root.iter(f"{_MAIN_NS}row"):
            if row.get("r") == "1":
                continue  # header

            cells: dict[str, str | float | None] = {}
            for c in row.findall(f"{_MAIN_NS}c"):
                col = _col_letters(c.get("r", ""))
                cells[col] = _cell_value(c, shared_strings)

            bye_val = cells.get("B")
            if not isinstance(bye_val, float):
                continue  # commentary / strategy / "how to play it" rows: no numeric Bye

            name = cells.get("A")
            adp = cells.get("C")
            rd_pk_raw = cells.get("D")
            risk = cells.get("E")
            note = cells.get("F")

            adp_round: int | None = None
            adp_pick: int | None = None
            if isinstance(rd_pk_raw, str) and "." in rd_pk_raw:
                head, _, tail = rd_pk_raw.partition(".")
                try:
                    adp_round, adp_pick = int(head), int(tail)
                except ValueError:
                    adp_round = adp_pick = None

            results.append(
                {
                    "name": name,
                    "normalized_name": normalize_name(name) if isinstance(name, str) else "",
                    "position": "DST",
                    "nfl_team": None,
                    "bye": int(bye_val),
                    "adp": float(adp) if isinstance(adp, (int, float)) else None,
                    "adp_rank": None,
                    "adp_round": adp_round,
                    "adp_pick": adp_pick,
                    "overall_tier": None,
                    "positional_tier": None,
                    "risk": risk if isinstance(risk, str) else None,
                    "risk_score": None,
                    "rookie": False,
                    "out_for_season": False,
                    "unpriced_risk": False,
                    "note": note if isinstance(note, str) and note else None,
                    "thesis": None,
                    "take_in_round": rd_pk_raw if isinstance(rd_pk_raw, str) else None,
                    "sleeper_category": None,
                    "catalyst": None,
                    "format_fit": None,
                    "flags": json.dumps([]),
                    "injury_tags": json.dumps([]),
                    "analyst_takes": json.dumps([]),
                    "sources": json.dumps([]),
                }
            )

        return results


# ---------------------------------------------------------------------------
# 1.6 -- strategy_rules.json
# ---------------------------------------------------------------------------

_SYNTHETIC_BLOCKS = ("positional_cliffs", "value_calc", "draft_slot_1_plan")


def load_strategy_rules(path: str | Path) -> list[dict]:
    """Parse `strategy_rules.json` into `board_heuristics`-shaped rows: one per entry in
    `heuristics` (keyed by its own `id`), plus one per synthetic key
    (`_positional_cliffs`, `_value_calc`, `_draft_slot_1_plan`) for the remaining
    top-level blocks. `payload` always carries the full source object as JSON."""
    data = json.loads(Path(path).read_text())

    rows: list[dict] = []
    for h in data.get("heuristics", []):
        rows.append(
            {
                "id": h["id"],
                "title": h["id"].replace("_", " ").title(),
                "body": h.get("rule"),
                "payload": json.dumps(h),
            }
        )

    for key in _SYNTHETIC_BLOCKS:
        if key in data:
            rows.append(
                {
                    "id": f"_{key}",
                    "title": key.replace("_", " ").title(),
                    "body": None,
                    "payload": json.dumps(data[key]),
                }
            )

    return rows


# ---------------------------------------------------------------------------
# 4.2 / 4.3 -- layered ESPN matcher
# ---------------------------------------------------------------------------

FUZZY_RATIO_THRESHOLD = 0.88

# Board DST rows carry the club's city+nickname (e.g. "Seattle Seahawks", "LA Rams",
# "New England") rather than an NFL team abbreviation -- unlike skill players, whose
# `team` field already lines up with `PRO_TEAM_MAP` values (verified against the real
# board: every value present is an actual `PRO_TEAM_MAP` abbreviation, or the sentinel
# "-"/"FA" for a player between teams). This maps every plausible board-style DST display
# name, normalized, to the abbreviation `EspnPlayerRef.nfl_team` uses for its D/ST refs.
_DST_TEAM_NAME_TO_ABBR: dict[str, str] = {
    normalize_name(name): abbr
    for name, abbr in {
        "Arizona Cardinals": "ARI",
        "Atlanta Falcons": "ATL",
        "Baltimore Ravens": "BAL",
        "Buffalo Bills": "BUF",
        "Carolina Panthers": "CAR",
        "Chicago Bears": "CHI",
        "Cincinnati Bengals": "CIN",
        "Cleveland Browns": "CLE",
        "Dallas Cowboys": "DAL",
        "Denver Broncos": "DEN",
        "Detroit Lions": "DET",
        "Green Bay Packers": "GB",
        "Houston Texans": "HOU",
        "Indianapolis Colts": "IND",
        "Jacksonville Jaguars": "JAX",
        "Kansas City Chiefs": "KC",
        "LA Chargers": "LAC",
        "Los Angeles Chargers": "LAC",
        "LA Rams": "LAR",
        "Los Angeles Rams": "LAR",
        "Las Vegas Raiders": "LV",
        "Miami Dolphins": "MIA",
        "Minnesota Vikings": "MIN",
        "New England": "NE",
        "New England Patriots": "NE",
        "New Orleans Saints": "NO",
        "New York Giants": "NYG",
        "NY Giants": "NYG",
        "New York Jets": "NYJ",
        "NY Jets": "NYJ",
        "Philadelphia Eagles": "PHI",
        "Pittsburgh Steelers": "PIT",
        "Seattle Seahawks": "SEA",
        "San Francisco 49ers": "SF",
        "Tampa Bay Buccaneers": "TB",
        "Tennessee Titans": "TEN",
        "Washington": "WAS",
        "Washington Commanders": "WAS",
    }.items()
}


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching one board player against the ESPN player universe.

    `candidates` is populated only on `unmatched` results produced by an ambiguity (more
    than one distinct ESPN player id tied at the same precedence level) -- it carries
    every tied candidate so a human can resolve it via `board_id_overrides`. It is always
    empty for a clean match (unique hit) or a plain no-hit unmatched result.
    """

    board_name: str
    espn_player_id: int | None
    match_method: str
    match_confidence: float
    candidates: tuple[EspnPlayerRef, ...] = field(default_factory=tuple)


def _dedupe_by_id(refs: list[EspnPlayerRef]) -> list[EspnPlayerRef]:
    seen: set[int] = set()
    deduped: list[EspnPlayerRef] = []
    for ref in refs:
        if ref.espn_player_id not in seen:
            seen.add(ref.espn_player_id)
            deduped.append(ref)
    return deduped


def _resolve(
    board_name: str, candidates: list[EspnPlayerRef], method: str, confidence: float
) -> MatchResult:
    """Apply the ambiguity rule: a unique candidate id wins outright; more than one
    distinct id assigns no match at all (never guess) and carries every candidate for
    human resolution."""
    deduped = _dedupe_by_id(candidates)
    if len(deduped) == 1:
        return MatchResult(board_name, deduped[0].espn_player_id, method, confidence)
    return MatchResult(board_name, None, "unmatched", 0.0, candidates=tuple(deduped))


def _match_dst(entry: dict, dst_by_team: dict[str, list[EspnPlayerRef]]) -> MatchResult:
    """4.3 -- defenses match by NFL team abbreviation only. Name-based methods are never
    attempted: ESPN's `fullName` for a D/ST is the club nickname ("Falcons D/ST"), never
    the city, so a name-normalized comparison against the board's "Seattle Seahawks"-style
    display name is guaranteed to miss."""
    name = entry["name"]
    abbr = entry.get("nfl_team") or _DST_TEAM_NAME_TO_ABBR.get(
        entry.get("normalized_name") or normalize_name(name)
    )
    if not abbr:
        return MatchResult(name, None, "unmatched", 0.0)
    candidates = dst_by_team.get(abbr, [])
    if not candidates:
        return MatchResult(name, None, "unmatched", 0.0)
    return _resolve(name, candidates, "exact", 1.0)


def match_board_players(
    board_entries: list[dict],
    universe: list[EspnPlayerRef],
    overrides: dict[str, int | None],
) -> list[MatchResult]:
    """Layered matcher: for each board entry, try each precedence level in order and
    take the first hit -- pure/sync, no DB or network access (both are the caller's job).

    Precedence, first hit wins:
      1. `override`      (1.0) -- `overrides[board_name]`, beats everything including DST.
      2. `exact`          (1.0) -- normalized name + position + nfl_team.
      3. `team_changed`   (0.9) -- normalized name + position.
      4. `name_only`      (0.8) -- normalized name.
      5. `fuzzy`          (0.6) -- SequenceMatcher ratio >= 0.88, same position only.
      6. `unmatched`      (0.0)

    DST entries (`position == "DST"`) skip straight from `override` to team-abbreviation
    matching (4.3) -- name-based tiers 2-5 are never attempted for them.

    Ambiguity rule: if a tier's candidates resolve to more than one distinct
    `espn_player_id`, the entry is recorded `unmatched` with every candidate carried in
    `MatchResult.candidates` rather than guessing.
    """
    by_exact: dict[tuple[str, str, str], list[EspnPlayerRef]] = {}
    by_team_changed: dict[tuple[str, str], list[EspnPlayerRef]] = {}
    by_name_only: dict[str, list[EspnPlayerRef]] = {}
    by_position: dict[str, list[EspnPlayerRef]] = {}
    dst_by_team: dict[str, list[EspnPlayerRef]] = {}

    normalized_refs: list[tuple[str, EspnPlayerRef]] = []
    for ref in universe:
        norm = normalize_name(ref.full_name)
        normalized_refs.append((norm, ref))
        if ref.is_dst:
            dst_by_team.setdefault(ref.nfl_team, []).append(ref)
            continue  # DST refs never enter the name-based indexes.
        by_exact.setdefault((norm, ref.position, ref.nfl_team), []).append(ref)
        by_team_changed.setdefault((norm, ref.position), []).append(ref)
        by_name_only.setdefault(norm, []).append(ref)
        by_position.setdefault(ref.position, []).append(ref)

    results: list[MatchResult] = []
    for entry in board_entries:
        name = entry["name"]
        position = entry["position"]

        if name in overrides:
            override_id = overrides[name]
            results.append(MatchResult(name, override_id, "override", 1.0))
            continue

        if position == "DST":
            results.append(_match_dst(entry, dst_by_team))
            continue

        normalized = entry.get("normalized_name") or normalize_name(name)
        nfl_team = entry.get("nfl_team")

        candidates = by_exact.get((normalized, position, nfl_team), []) if nfl_team else []
        if candidates:
            results.append(_resolve(name, candidates, "exact", 1.0))
            continue

        candidates = by_team_changed.get((normalized, position), [])
        if candidates:
            results.append(_resolve(name, candidates, "team_changed", 0.9))
            continue

        candidates = by_name_only.get(normalized, [])
        if candidates:
            results.append(_resolve(name, candidates, "name_only", 0.8))
            continue

        fuzzy_candidates = [
            ref
            for ref in by_position.get(position, [])
            if difflib.SequenceMatcher(None, normalized, normalize_name(ref.full_name)).ratio()
            >= FUZZY_RATIO_THRESHOLD
        ]
        if fuzzy_candidates:
            results.append(_resolve(name, fuzzy_candidates, "fuzzy", 0.6))
            continue

        results.append(MatchResult(name, None, "unmatched", 0.0))

    return results


# ---------------------------------------------------------------------------
# 4.4 -- bye reconciliation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ByeDiscrepancy:
    """One board player whose board-sourced bye disagrees with the ESPN platform's --
    ESPN wins; the caller is expected to overwrite `BoardPlayer.bye` with `platform_bye`."""

    board_name: str
    espn_player_id: int
    board_bye: int | None
    platform_bye: int


def reconcile_byes(
    board_entries: list[dict], platform_byes: dict[int, int | None]
) -> list[ByeDiscrepancy]:
    """Compare each matched board entry's `bye` against the platform's `bye_week` for the
    same `espn_player_id`, reporting every disagreement. Pure/sync: does not mutate
    `board_entries` and does not touch the DB -- the caller applies the platform value
    (ESPN wins) and logs this list.

    Each entry needs `name`, `bye`, and `espn_player_id` (`None` skips the entry --
    unmatched board players have no platform bye to compare against). A platform bye of
    `None` (unknown) also skips the entry rather than being treated as a disagreement.
    """
    discrepancies: list[ByeDiscrepancy] = []
    for entry in board_entries:
        espn_id = entry.get("espn_player_id")
        if espn_id is None:
            continue
        platform_bye = platform_byes.get(espn_id)
        if platform_bye is None:
            continue
        board_bye = entry.get("bye")
        if board_bye != platform_bye:
            discrepancies.append(ByeDiscrepancy(entry["name"], espn_id, board_bye, platform_bye))
    return discrepancies
