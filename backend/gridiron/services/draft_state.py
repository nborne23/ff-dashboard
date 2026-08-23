"""Live draft state: the write path for picks, the undrafted pool / roster reads the
recommender consumes, and league-shape resolution.

**Design D13 -- explicit current-pick tracking.** `current_overall_pick` is a
user-correctable value persisted on the single `DraftSession` row, NEVER inferred from
`count(draft_picks)`. During a real draft the user marks only *some* picks (they skip
picks other teams make that don't matter to them, catch up in bursts, etc.), so an
inferred count silently drifts below the true overall pick number and every
tier-urgency / `picks_until_next` calculation downstream then fires against a wrong
value with no visible symptom. `record_pick` advances the counter by exactly one on
every call (even when the caller supplies a far-ahead `overall_pick` explicitly) --
jumping the counter to `overall_pick + 1` would silently paper over the user having
skipped entering several picks. `PUT /api/draft/current-pick`
(`set_current_overall_pick`) is the deliberate, explicit correction mechanism for that
case; nothing here tries to be clever about it.

`record_pick` is the single write path both manual entry (phase 3) and the ESPN poller
(phase 5, `source="espn"`) go through, so every downstream consumer (differ
fingerprints, SSE publish, the current-pick counter) only has to be wired up once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.draft_board import PACKAGE_DIR
from backend.gridiron.errors import DraftPickConflictError
from backend.gridiron.models import BoardPlayer, DraftPick, DraftSession, League
from backend.gridiron.platforms.espn.slot_table import UnknownSlotError, espn_slot_name
from backend.gridiron.services import differ
from backend.gridiron.services.draft_pick_math import picks_until_next as _picks_until_next
from backend.gridiron.services.draft_pick_math import round_for_pick
from backend.gridiron.services.draft_recommender import Candidate, LeagueShape

# ---------------------------------------------------------------------------
# Candidate adapter
# ---------------------------------------------------------------------------


def to_candidate(board_player: BoardPlayer, *, off_board: bool = False) -> Candidate:
    """`BoardPlayer` ORM row -> the recommender's plain-data `Candidate`. `flags` is
    JSON-in-TEXT on the model (see `draft_board.py`'s import) -- decoded to a tuple
    here, the boundary where every other reader of `BoardPlayer.flags` also decodes it.
    """
    flags: tuple[str, ...] = tuple(json.loads(board_player.flags) if board_player.flags else [])
    return Candidate(
        name=board_player.name,
        position=board_player.position,
        nfl_team=board_player.nfl_team,
        bye=board_player.bye,
        adp_rank=board_player.adp_rank,
        overall_tier=board_player.overall_tier,
        positional_tier=board_player.positional_tier,
        risk_score=board_player.risk_score,
        unpriced_risk=board_player.unpriced_risk,
        flags=flags,
        off_board=off_board,
    )


# ---------------------------------------------------------------------------
# Picks: record / undo / list
# ---------------------------------------------------------------------------


async def _next_unused_overall_pick(session: AsyncSession) -> int:
    """The pick number to use when the caller doesn't supply one explicitly: D13's own
    `current_overall_pick` -- "the pick happening now" -- NOT the earliest unused number
    starting from 1. The frontend's MarkDrafted control never sends `overall_pick`, so
    this is the path essentially every real UI-driven pick goes through; using the
    counter (rather than backfilling the first historical gap) is what makes consecutive
    taps during burst entry land on consecutive real pick numbers, in step with the
    `current_overall_pick + 1` advance `record_pick` performs right after. Only steps
    forward past `current_overall_pick` if that exact slot is somehow already taken (a
    stale UI resubmission, or a manual `overall_pick` write that raced ahead of it) --
    it never looks backward into earlier rounds for a hole to fill.
    """
    session_row = await _get_or_create_session_row(session)
    n = session_row.current_overall_pick or 1
    result = await session.execute(select(DraftPick.overall_pick))
    used = {row[0] for row in result.all()}
    while n in used:
        n += 1
    return n


async def _get_or_create_session_row(session: AsyncSession) -> DraftSession:
    result = await session.execute(select(DraftSession).order_by(DraftSession.id).limit(1))
    row = result.scalars().first()
    if row is not None:
        return row
    row = DraftSession(status="manual", poll_interval_seconds=3)
    session.add(row)
    await session.flush()
    return row


async def record_pick(
    session: AsyncSession,
    *,
    player_name: str | None = None,
    board_player_id: int | None = None,
    is_my_pick: bool = False,
    drafted_by_team: str | None = None,
    overall_pick: int | None = None,
    source: str = "manual",
    espn_player_id: int | None = None,
) -> DraftPick:
    """Record one draft pick. The single write path for both manual entry and the ESPN
    poller (phase 5, `source="espn"`).

    Resolves the board player by `board_player_id` (preferred) or `player_name`, and
    copies `position` from it when found -- an off-board name (e.g. a rookie/DST not on
    this board, or a typo caught later) is still recorded, just without a `position` or
    `board_player_id`.

    When `overall_pick` is omitted, `current_overall_pick` (D13) is used -- see
    `_next_unused_overall_pick`. A duplicate
    `overall_pick` naming a *different* player raises `DraftPickConflictError` when the
    caller is manual (`source="manual"`) -- an ESPN-sourced pick at an already-recorded
    slot is allowed to overwrite it (phase 5's poller correcting a manual guess).

    Advances the session's `current_overall_pick` by exactly one on every call (D13) --
    never jumps to `overall_pick + 1`, even when the caller supplies a far-ahead pick
    number explicitly. Use `set_current_overall_pick` to correct the counter directly.
    """
    board_player: BoardPlayer | None = None
    if board_player_id is not None:
        board_player = await session.get(BoardPlayer, board_player_id)
    elif player_name is not None:
        result = await session.execute(select(BoardPlayer).where(BoardPlayer.name == player_name))
        board_player = result.scalars().first()

    resolved_name = (
        player_name
        if player_name is not None
        else (board_player.name if board_player is not None else None)
    )
    if resolved_name is None:
        raise ValueError("record_pick requires player_name or a resolvable board_player_id")

    pick_number = (
        overall_pick if overall_pick is not None else await _next_unused_overall_pick(session)
    )

    existing = await session.execute(select(DraftPick).where(DraftPick.overall_pick == pick_number))
    existing_row = existing.scalars().first()
    if existing_row is not None:
        if existing_row.player_name != resolved_name and source == "manual":
            raise DraftPickConflictError(pick_number, existing_row.player_name)
        # ESPN source (or a same-player re-confirm): update the existing row in place
        # rather than violating the `overall_pick` UNIQUE constraint with a second insert.
        existing_row.player_name = resolved_name
        existing_row.board_player_id = board_player.id if board_player is not None else None
        existing_row.espn_player_id = espn_player_id
        existing_row.position = board_player.position if board_player is not None else None
        existing_row.drafted_by_team = drafted_by_team
        existing_row.is_my_pick = is_my_pick
        existing_row.source = source
        pick = existing_row
    else:
        pick = DraftPick(
            overall_pick=pick_number,
            round=round_for_pick(pick_number, _STATIC_TEAMS),
            board_player_id=board_player.id if board_player is not None else None,
            espn_player_id=espn_player_id,
            player_name=resolved_name,
            position=board_player.position if board_player is not None else None,
            drafted_by_team=drafted_by_team,
            is_my_pick=is_my_pick,
            source=source,
        )
        session.add(pick)

    session_row = await _get_or_create_session_row(session)
    current = session_row.current_overall_pick or 1
    session_row.current_overall_pick = current + 1
    session_row.current_round = round_for_pick(session_row.current_overall_pick, _STATIC_TEAMS)

    # Commit -> fingerprint -> publish, all in the write path itself (not left to the
    # API layer) so EVERY caller (manual entry today, the phase-5 ESPN poller
    # tomorrow) gets the SSE `data.changed` event for free -- task 3.5's "manual picks
    # publish it too" requirement, satisfied by construction rather than by remembering
    # to call it from each router handler.
    await session.commit()
    fingerprints = await differ.draft_fingerprints(session)
    differ.diff_and_publish(fingerprints)
    return pick


async def undo_last_pick(session: AsyncSession) -> DraftPick | None:
    """Delete the pick at the highest `overall_pick` (regardless of `source`) and return
    it. Restores state exactly: the player returns to the undrafted pool, roster counts
    revert, and D13's `current_overall_pick` counter is decremented by one (floored at
    1) to match -- `record_pick` advanced it by one, so undo must give that back.
    """
    result = await session.execute(select(DraftPick).order_by(DraftPick.overall_pick.desc()))
    last = result.scalars().first()
    if last is None:
        return None

    # Capture the id/values before delete+commit expires attribute access on some
    # SQLAlchemy configurations; harmless (a no-op copy) under this app's own
    # `expire_on_commit=False` sessionmaker, but keeps this function correct even if a
    # caller wires up a differently-configured session.
    undone = DraftPick(
        id=last.id,
        overall_pick=last.overall_pick,
        round=last.round,
        board_player_id=last.board_player_id,
        espn_player_id=last.espn_player_id,
        player_name=last.player_name,
        position=last.position,
        drafted_by_team=last.drafted_by_team,
        is_my_pick=last.is_my_pick,
        source=last.source,
    )

    await session.delete(last)

    session_row = await _get_or_create_session_row(session)
    current = session_row.current_overall_pick or 1
    session_row.current_overall_pick = max(current - 1, 1)
    session_row.current_round = round_for_pick(session_row.current_overall_pick, _STATIC_TEAMS)

    await session.commit()
    fingerprints = await differ.draft_fingerprints(session)
    differ.diff_and_publish(fingerprints)
    return undone


async def list_picks(session: AsyncSession) -> list[DraftPick]:
    result = await session.execute(select(DraftPick).order_by(DraftPick.overall_pick))
    return list(result.scalars().all())


async def recent_picks(session: AsyncSession, limit: int = 5) -> list[Candidate]:
    """The last `limit` picks (any source, any team) that resolve to a board player, as
    `Candidate`s -- feeds `recommend`'s "a peer in this tier was JUST taken" reason
    enrichment. Off-board picks (no `board_player_id`) are skipped; they can't carry a
    `positional_tier` for that comparison anyway."""
    result = await session.execute(
        select(BoardPlayer)
        .join(DraftPick, DraftPick.board_player_id == BoardPlayer.id)
        .order_by(DraftPick.overall_pick.desc())
        .limit(limit)
    )
    return [to_candidate(bp) for bp in result.scalars().all()]


async def my_roster(session: AsyncSession) -> list[Candidate]:
    """Board players for picks with `is_my_pick=True`, as recommender `Candidate`s.
    Skips picks with no resolvable `board_player_id` (an off-board pick can't become a
    scored `Candidate` -- it simply doesn't participate in need/bye-collision math)."""
    result = await session.execute(
        select(BoardPlayer)
        .join(DraftPick, DraftPick.board_player_id == BoardPlayer.id)
        .where(DraftPick.is_my_pick.is_(True))
        .order_by(DraftPick.overall_pick)
    )
    return [to_candidate(bp) for bp in result.scalars().all()]


async def undrafted_pool(session: AsyncSession) -> list[Candidate]:
    """All `board_players` minus every drafted player (any source), excluding
    `out_for_season=True`, ordered by `adp_rank` with NULLs last (dialect-neutral: no
    `NULLS LAST`, just an `is_(None)` sort key ahead of the value itself)."""
    drafted_ids = select(DraftPick.board_player_id).where(DraftPick.board_player_id.is_not(None))
    result = await session.execute(
        select(BoardPlayer)
        .where(
            BoardPlayer.out_for_season.is_(False),
            BoardPlayer.id.not_in(drafted_ids),
        )
        .order_by(BoardPlayer.adp_rank.is_(None), BoardPlayer.adp_rank)
    )
    return [to_candidate(bp) for bp in result.scalars().all()]


# ---------------------------------------------------------------------------
# D13: explicit current-pick tracking
# ---------------------------------------------------------------------------


async def get_current_overall_pick(session: AsyncSession) -> int:
    session_row = await _get_or_create_session_row(session)
    return session_row.current_overall_pick or 1


async def get_session_status(session: AsyncSession) -> str:
    """The lazily-created `DraftSession` row's `status` (e.g. `"manual"` before phase 5
    ever arms a poller). Shares the same lazy-create as `get_current_overall_pick` --
    calling either on a fresh DB creates the one row both read from."""
    session_row = await _get_or_create_session_row(session)
    return session_row.status


async def set_current_overall_pick(session: AsyncSession, value: int) -> int:
    if value < 1:
        raise ValueError("current_overall_pick must be >= 1")
    session_row = await _get_or_create_session_row(session)
    session_row.current_overall_pick = value
    session_row.current_round = round_for_pick(value, _STATIC_TEAMS)
    await session.flush()
    return value


def picks_until_next(current_pick: int, my_picks: list[int]) -> int | None:
    """Wraps `draft_pick_math.picks_until_next`, returning `None` (draft-over, no
    upcoming turn for the user) instead of letting its `ValueError` propagate past the
    user's last scheduled pick -- an API 500 on the last pick of the draft is exactly
    the kind of silent-until-draft-night bug this module exists to avoid."""
    try:
        return _picks_until_next(current_pick, my_picks)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 3.2 -- league-shape resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingsConflict:
    """One field's static-vs-ESPN comparison for the UI's unconfirmed-settings banner."""

    field: str
    static_value: Any
    espn_value: Any | None
    resolved_value: Any
    confirmed_by_espn: bool
    note: str = ""


_STATIC_CONFIG_PATH = PACKAGE_DIR / "league_config.json"
_DEFAULT_BENCH = 6
# Fallback team count used by `record_pick`/`undo_last_pick` for `round_for_pick` before
# any league-shape resolution has happened this call -- always the static config's value
# (round numbers on `DraftPick` rows are informational display data, not read by the
# recommender, which takes `LeagueShape.teams` fresh from `resolve_league_shape` on every
# call instead).
_STATIC_TEAMS: int = json.loads(_STATIC_CONFIG_PATH.read_text())["teams"]


def _load_static_config() -> dict[str, Any]:
    return json.loads(_STATIC_CONFIG_PATH.read_text())


# Internal starters vocabulary this module (and the recommender) understands.
_STARTER_POSITIONS = {"QB", "RB", "WR", "TE", "FLEX", "DST", "K"}


def _starters_from_lineup_slot_counts(counts: dict[int, int]) -> tuple[dict[str, int], int]:
    """Translate ESPN `lineupSlotCounts` (`lineupSlotId -> count`) into an internal
    `starters` dict + bench count, via `slot_table.espn_slot_name` -- reused, not
    reimplemented (see `platforms/espn/slot_table.py`'s own "keep this the one lookup
    table" rationale). Raises `UnknownSlotError` untranslated on an id this league's
    internal roster shape has no slot for (IDP/kicker-adjacent slots); callers decide how
    to surface that as a conflict rather than crashing the endpoint.
    """
    starters: dict[str, int] = {}
    bench = 0
    for slot_id, count in counts.items():
        name = espn_slot_name(int(slot_id))
        if name == "BN":
            bench = count
        elif name == "IR":
            continue  # IR doesn't occupy a starter or bench slot in our internal shape
        elif name in _STARTER_POSITIONS:
            starters[name] = starters.get(name, 0) + count
        else:
            raise UnknownSlotError(int(slot_id))
    return starters, bench


async def _espn_lineup_slot_counts(session: AsyncSession) -> dict[int, int] | None:
    """ESPN `settings.rosterSettings.lineupSlotCounts` for the primary connected ESPN
    league, if it were persisted anywhere. Nothing in this codebase persists the raw
    `mSettings` roster-settings payload today (`platforms/espn/client.py`/`mapper.py`
    touch it only transiently, in-request) -- `League` has no raw-settings column -- so
    this always returns `None` in phase 3. It exists as the one seam phase 5 (or an
    ESPN-settings-caching change) fills in later, so `_starters_from_lineup_slot_counts`
    above has a real, exercised caller shape rather than dead code with no plausible
    input.
    """
    return None


async def _espn_league_row(session: AsyncSession) -> League | None:
    result = await session.execute(
        select(League)
        .where(League.platform == "espn", League.is_enabled.is_(True))
        .order_by(League.id)
    )
    return result.scalars().first()


async def resolve_league_shape(
    session: AsyncSession,
) -> tuple[LeagueShape, list[SettingsConflict]]:
    """Resolve the league's shape for the recommender, preferring ESPN `mSettings` data
    already in the DB and falling back to the static, user-authored-but-unconfirmed
    `draft_board/league_config.json`. Every field the static file supplies is reported
    as a `SettingsConflict` (even when ESPN agrees or is silent) so the UI never has to
    guess which numbers are confirmed -- see the module + task docstrings for D13's
    sibling rationale on why nothing here is inferred quietly.
    """
    static = _load_static_config()
    static_starters: dict[str, int] = dict(static["roster"]["starters"])
    static_flex = tuple(static["roster"]["flex_eligible"])
    static_bench = static["roster"].get("bench") or _DEFAULT_BENCH
    static_teams = static["teams"]
    static_slot = static["user_draft_slot"]

    espn_league = await _espn_league_row(session)
    espn_teams = espn_league.team_count if espn_league is not None else None

    lineup_counts = await _espn_lineup_slot_counts(session)
    espn_starters: dict[str, int] | None = None
    espn_bench: int | None = None
    parse_note = ""
    if lineup_counts is not None:
        try:
            espn_starters, espn_bench = _starters_from_lineup_slot_counts(lineup_counts)
        except UnknownSlotError as exc:
            parse_note = f"could not fully parse ESPN roster settings: {exc}"

    resolved_teams = espn_teams if espn_teams is not None else static_teams
    resolved_starters = espn_starters if espn_starters is not None else static_starters
    resolved_bench = espn_bench if espn_bench is not None else static_bench
    # No ESPN source exists yet for flex-eligibility or draft slot (mSettings doesn't
    # carry either in a form this app parses) -- always the static value.
    resolved_flex = static_flex
    resolved_slot = static_slot
    resolved_rounds = sum(resolved_starters.values()) + resolved_bench

    league_shape = LeagueShape(
        teams=resolved_teams,
        starters=resolved_starters,
        flex_eligible=resolved_flex,
        rounds=resolved_rounds,
        slot=resolved_slot,
    )

    espn_reachable = espn_league is not None or lineup_counts is not None
    conflicts = [
        SettingsConflict(
            field="teams",
            static_value=static_teams,
            espn_value=espn_teams,
            resolved_value=resolved_teams,
            confirmed_by_espn=espn_teams is not None,
        ),
        SettingsConflict(
            field="starters",
            static_value=static_starters,
            espn_value=espn_starters,
            resolved_value=resolved_starters,
            confirmed_by_espn=espn_starters is not None,
            note=parse_note,
        ),
        SettingsConflict(
            field="bench",
            static_value=static_bench,
            espn_value=espn_bench,
            resolved_value=resolved_bench,
            confirmed_by_espn=espn_bench is not None,
        ),
        SettingsConflict(
            field="flex_eligible",
            static_value=list(static_flex),
            espn_value=None,
            resolved_value=list(resolved_flex),
            confirmed_by_espn=False,
        ),
        SettingsConflict(
            field="user_draft_slot",
            static_value=static_slot,
            espn_value=None,
            resolved_value=resolved_slot,
            confirmed_by_espn=False,
        ),
        # Synthetic, banner-level entry (underscore-prefixed like `board_heuristics`'
        # own synthetic ids) -- the "could not read ESPN at all" flag the task calls for,
        # expressed as one more list entry rather than widening the return signature.
        SettingsConflict(
            field="_espn_connectivity",
            static_value=None,
            espn_value="connected" if espn_reachable else None,
            resolved_value=(
                "espn-backed where available" if espn_reachable else "static fallback (unconfirmed)"
            ),
            confirmed_by_espn=espn_reachable,
        ),
    ]

    return league_shape, conflicts
