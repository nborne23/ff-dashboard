"""Task 4.5 -- board/ESPN match resolution: read live `BoardPlayer` match state (with
candidate ESPN players for anything below the 0.9 confidence gate) and write hand
overrides that survive every subsequent `run_import` re-run.

**Universe caching -- decision (contract gap, documented per the task instructions):**
`GET /api/draft/matches` needs the ESPN player universe to resolve candidates for
low-confidence rows, but fetching it live on every request would hit a
multi-thousand-player upstream payload on every page load. Two options existed:
persist it via `services/cache.py`'s `http_cache` table, or keep an in-memory cache.
`http_cache` was rejected: its own docstring (design.md D7) is explicit that "read
endpoints ALWAYS serve whatever is cached; they never fetch from Yahoo/ESPN on a miss
... Only the scheduler is expected to call `set`" -- writing to it from a GET handler
would contradict that contract. Instead this module keeps a simple module-level
in-memory cache (`_universe_cache`), the same idiom already used by
`services/fantasy_service.py` / `services/differ.py` / `services/events.py` (each with
its own `reset_state()` test hook, mirrored here). It is lazily populated on first use,
keyed by year, TTL'd, and `fetch_universe` is injectable exactly like
`draft_board.run_import`'s own parameter so tests never touch the network.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.draft_board import _default_espn_year
from backend.gridiron.models import BoardIdOverride, BoardPlayer
from backend.gridiron.platforms.espn.draft import (
    PLAYERS_WL_BASE,
    EspnPlayerRef,
    fetch_player_universe,
)
from backend.gridiron.services.draft_board import match_board_players

logger = logging.getLogger(__name__)

# Below this, a board entry is not confidently matched -- 4.5's UI-facing gate.
CONFIDENCE_THRESHOLD = 0.9

_UNIVERSE_TTL = timedelta(hours=12)
_universe_cache: dict[int, tuple[datetime, list[EspnPlayerRef]]] = {}


def reset_state() -> None:
    """Test hook -- clears the in-memory universe cache. Call from an autouse fixture
    alongside `fantasy_service.reset_state()` etc. so `/matches` tests never leak a
    cached (or injected-stub) universe across test cases."""
    _universe_cache.clear()


async def get_espn_universe(
    year: int,
    fetch_universe: Callable[[], Awaitable[list[EspnPlayerRef]]] | None = None,
) -> list[EspnPlayerRef]:
    """Cache-first lookup of the parsed ESPN player universe for `year`. See the module
    docstring for why this is an in-memory cache rather than `http_cache`.

    On a fetch failure, falls back to a stale cached entry if one exists (better than an
    empty candidate list); with no cache at all, returns `[]` -- matching
    `draft_board.run_import`'s own offline-import behavior (never raises).
    """
    cached = _universe_cache.get(year)
    now = datetime.now(UTC)
    if cached is not None and now - cached[0] < _UNIVERSE_TTL:
        return cached[1]

    try:
        if fetch_universe is not None:
            universe = await fetch_universe()
        else:
            async with httpx.AsyncClient(base_url=PLAYERS_WL_BASE, timeout=10) as http_client:
                universe = await fetch_player_universe(year, http_client=http_client)
    except Exception:
        logger.warning("ESPN player universe fetch failed for /api/draft/matches", exc_info=True)
        return cached[1] if cached is not None else []

    _universe_cache[year] = (now, universe)
    return universe


@dataclass(frozen=True)
class BoardMatch:
    board_player_name: str
    espn_player_id: int | None
    match_method: str
    match_confidence: float
    candidates: tuple[EspnPlayerRef, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MatchesReport:
    matches: list[BoardMatch]
    method_counts: dict[str, int]
    below_threshold_count: int


async def list_matches(
    session: AsyncSession,
    *,
    espn_year: int | None = None,
    fetch_universe: Callable[[], Awaitable[list[EspnPlayerRef]]] | None = None,
) -> MatchesReport:
    """Every board player's match state, summary counts, and (for rows below the 0.9
    gate) candidate ESPN players to resolve against.

    `run_import` persists only the resolved `espn_player_id`/`match_method`/
    `match_confidence` per row -- `MatchResult.candidates` (the tied-candidate list on
    an ambiguity) is never written to the DB. So candidates are recovered here by
    re-running the pure `match_board_players` matcher, but ONLY over the below-threshold
    rows -- passing the full board would be wasted work for rows already confidently
    resolved. This is safe: `match_board_players` builds its lookup indexes from the
    UNIVERSE argument, not from the board-entries argument, so restricting the entries
    list to a subset never changes any individual entry's own result. `overrides={}` is
    also safe here -- any board player with a live override already sits at
    match_confidence=1.0 ("override" method) and so is excluded from `below` by
    construction, meaning the matcher's override branch never needs to fire for this
    call.
    """
    result = await session.execute(select(BoardPlayer))
    rows = list(result.scalars().all())

    method_counts: dict[str, int] = {}
    for row in rows:
        method_counts[row.match_method] = method_counts.get(row.match_method, 0) + 1

    below = [row for row in rows if row.match_confidence < CONFIDENCE_THRESHOLD]

    universe_by_id: dict[int, EspnPlayerRef] = {}
    candidates_by_name: dict[str, tuple[EspnPlayerRef, ...]] = {}
    if below:
        universe = await get_espn_universe(
            espn_year if espn_year is not None else _default_espn_year(), fetch_universe
        )
        universe_by_id = {ref.espn_player_id: ref for ref in universe}

        entries = [
            {
                "name": row.name,
                "position": row.position,
                "normalized_name": row.normalized_name,
                "nfl_team": row.nfl_team,
            }
            for row in below
        ]
        fresh_results = match_board_players(entries, universe, overrides={})
        candidates_by_name = {r.board_name: r.candidates for r in fresh_results}

    matches: list[BoardMatch] = []
    for row in rows:
        candidates: tuple[EspnPlayerRef, ...] = ()
        if row.match_confidence < CONFIDENCE_THRESHOLD:
            # Ambiguous ties recovered by the fresh re-match, if any...
            candidates = candidates_by_name.get(row.name, ())
            if not candidates and row.espn_player_id is not None:
                # ...otherwise a unique-but-low-confidence match (team_changed below
                # 0.9 can't happen -- it's exactly 0.9 -- but name_only/fuzzy can): show
                # the one resolved candidate itself so the human can confirm or reject
                # it, rather than an empty list for a row that DOES have a match.
                ref = universe_by_id.get(row.espn_player_id)
                if ref is not None:
                    candidates = (ref,)
            # A genuinely zero-hit "unmatched" row (no candidates at any tier) is left
            # with an empty tuple -- still actionable via the explicit-no-match override.
        matches.append(
            BoardMatch(
                board_player_name=row.name,
                espn_player_id=row.espn_player_id,
                match_method=row.match_method,
                match_confidence=row.match_confidence,
                candidates=candidates,
            )
        )

    return MatchesReport(
        matches=matches,
        method_counts=method_counts,
        below_threshold_count=len(below),
    )


async def set_override(
    session: AsyncSession, board_player_name: str, espn_player_id: int | None
) -> BoardPlayer | None:
    """Write (or update) the `board_id_overrides` row for `board_player_name` and apply
    it immediately to the live `BoardPlayer` row. Returns `None` when the name isn't a
    known board player (the router turns that into a 404).

    Because `run_import` always re-applies every `board_id_overrides` row regardless of
    a row's current sticky state (see that module's docstring), this decision survives
    every subsequent re-import without any special-casing here.
    """
    result = await session.execute(select(BoardPlayer).where(BoardPlayer.name == board_player_name))
    board_player = result.scalars().first()
    if board_player is None:
        return None

    override_row = await session.get(BoardIdOverride, board_player_name)
    if override_row is None:
        session.add(
            BoardIdOverride(board_player_name=board_player_name, espn_player_id=espn_player_id)
        )
    else:
        override_row.espn_player_id = espn_player_id

    board_player.espn_player_id = espn_player_id
    board_player.match_method = "override"
    board_player.match_confidence = 1.0

    await session.commit()
    return board_player
