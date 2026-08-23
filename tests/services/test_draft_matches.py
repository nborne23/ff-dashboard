"""`services/draft_matches.py` -- task 4.5: match-state reads (with recovered candidate
ESPN players for anything below the 0.9 confidence gate), override writes, and the
in-memory universe cache's call-count behavior (the actual proof it caches rather than
fetching live on every call)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, BoardIdOverride, BoardPlayer
from backend.gridiron.platforms.espn.draft import EspnPlayerRef
from backend.gridiron.services import draft_matches


@pytest.fixture(autouse=True)
def _reset_module_state():
    draft_matches.reset_state()
    yield
    draft_matches.reset_state()


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "draft-matches.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _ref(espn_id: int, name: str, position: str, team: str) -> EspnPlayerRef:
    return EspnPlayerRef(
        espn_player_id=espn_id, full_name=name, position=position, nfl_team=team, is_dst=False
    )


def _player(
    name: str,
    *,
    position: str = "RB",
    espn_player_id: int | None = None,
    match_method: str = "unmatched",
    match_confidence: float = 0.0,
    nfl_team: str | None = None,
) -> BoardPlayer:
    return BoardPlayer(
        name=name,
        normalized_name=name.lower(),
        position=position,
        nfl_team=nfl_team,
        espn_player_id=espn_player_id,
        match_method=match_method,
        match_confidence=match_confidence,
    )


async def seed(session_factory, players: list[BoardPlayer]) -> None:
    async with session_factory() as session:
        for p in players:
            session.add(p)
        await session.commit()


def _counting_fetch(universe: list[EspnPlayerRef]):
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return universe

    return fetch, calls


# ---------------------------------------------------------------------------
# list_matches: counts, candidates, threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_matches_reports_method_counts_and_below_threshold(session_factory) -> None:
    await seed(
        session_factory,
        [
            _player("Exact Guy", match_method="exact", match_confidence=1.0, espn_player_id=1),
            _player(
                "Team Changed Guy",
                match_method="team_changed",
                match_confidence=0.9,
                espn_player_id=2,
            ),
            _player("Fuzzy Guy", match_method="fuzzy", match_confidence=0.6, espn_player_id=3),
        ],
    )
    fetch, _ = _counting_fetch([])
    async with session_factory() as session:
        report = await draft_matches.list_matches(session, fetch_universe=fetch)

    assert report.method_counts == {"exact": 1, "team_changed": 1, "fuzzy": 1}
    # team_changed sits AT 0.9, not below it -- only Fuzzy Guy is below threshold.
    assert report.below_threshold_count == 1


@pytest.mark.asyncio
async def test_real_zero_below_threshold_never_touches_the_universe_fetch(session_factory) -> None:
    """Mirrors the real committed board: every row confidently matched. The universe
    fetch must never even be attempted -- if it were, this stub raising would fail the
    test, proving the fetch path is skipped entirely rather than merely fast."""
    await seed(
        session_factory,
        [_player("Exact Guy", match_method="exact", match_confidence=1.0, espn_player_id=1)],
    )

    async def boom():
        raise AssertionError("universe fetch must not be called when nothing is below threshold")

    async with session_factory() as session:
        report = await draft_matches.list_matches(session, fetch_universe=boom)

    assert report.below_threshold_count == 0
    assert report.matches[0].candidates == ()


@pytest.mark.asyncio
async def test_ambiguous_low_confidence_row_recovers_tied_candidates(session_factory) -> None:
    """Two ESPN players share a normalized name at the same position -- `unmatched`
    (0.0 confidence) with no resolved id, but the fresh re-match must recover both tied
    candidates so the human can pick between them."""
    await seed(session_factory, [_player("Amb Guy", position="WR", match_method="unmatched")])
    universe = [_ref(10, "Amb Guy", "WR", "SF"), _ref(11, "Amb Guy", "WR", "NYJ")]
    fetch, calls = _counting_fetch(universe)

    async with session_factory() as session:
        report = await draft_matches.list_matches(session, fetch_universe=fetch)

    match = next(m for m in report.matches if m.board_player_name == "Amb Guy")
    assert match.espn_player_id is None
    assert {c.espn_player_id for c in match.candidates} == {10, 11}


@pytest.mark.asyncio
async def test_unique_low_confidence_row_shows_its_own_resolved_match_as_the_candidate(
    session_factory,
) -> None:
    """A name_only match (0.8, unique) already has a resolved espn_player_id in the DB
    -- the fresh re-match won't populate MatchResult.candidates for a unique hit (per
    match_board_players' own contract), so this must fall back to looking the resolved
    id up in the universe and offering it as the sole candidate."""
    await seed(
        session_factory,
        [
            _player(
                "Name Only Guy",
                position="RB",
                match_method="name_only",
                match_confidence=0.8,
                espn_player_id=42,
            )
        ],
    )
    universe = [_ref(42, "Name Only Guy", "RB", "KC")]
    fetch, calls = _counting_fetch(universe)

    async with session_factory() as session:
        report = await draft_matches.list_matches(session, fetch_universe=fetch)

    match = next(m for m in report.matches if m.board_player_name == "Name Only Guy")
    assert len(match.candidates) == 1
    assert match.candidates[0].espn_player_id == 42


@pytest.mark.asyncio
async def test_zero_hit_unmatched_row_has_no_candidates_but_is_still_listed(
    session_factory,
) -> None:
    await seed(session_factory, [_player("Nobody Guy", position="RB", match_method="unmatched")])
    fetch, _ = _counting_fetch([])

    async with session_factory() as session:
        report = await draft_matches.list_matches(session, fetch_universe=fetch)

    match = next(m for m in report.matches if m.board_player_name == "Nobody Guy")
    assert match.candidates == ()
    assert match.espn_player_id is None


@pytest.mark.asyncio
async def test_universe_fetch_is_cached_across_calls(session_factory) -> None:
    """The actual proof of the caching decision: two separate `list_matches` calls
    against the same (still-below-threshold) data must only invoke the injected fetch
    once -- the second call must be served from the in-memory cache."""
    await seed(session_factory, [_player("Fuzzy Guy", position="RB", match_method="unmatched")])
    universe = [_ref(1, "Fuzzy Guy", "RB", "KC")]
    fetch, calls = _counting_fetch(universe)

    async with session_factory() as session:
        await draft_matches.list_matches(session, fetch_universe=fetch)
    async with session_factory() as session:
        await draft_matches.list_matches(session, fetch_universe=fetch)

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_reset_state_clears_the_cache(session_factory) -> None:
    await seed(session_factory, [_player("Fuzzy Guy", position="RB", match_method="unmatched")])
    universe = [_ref(1, "Fuzzy Guy", "RB", "KC")]
    fetch, calls = _counting_fetch(universe)

    async with session_factory() as session:
        await draft_matches.list_matches(session, fetch_universe=fetch)

    draft_matches.reset_state()

    async with session_factory() as session:
        await draft_matches.list_matches(session, fetch_universe=fetch)

    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# set_override
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_override_writes_the_override_row_and_updates_the_board_player(
    session_factory,
) -> None:
    await seed(session_factory, [_player("Some Guy", position="RB")])

    async with session_factory() as session:
        updated = await draft_matches.set_override(session, "Some Guy", 999)

    assert updated.espn_player_id == 999
    assert updated.match_method == "override"
    assert updated.match_confidence == 1.0

    async with session_factory() as session:
        override_row = await session.get(BoardIdOverride, "Some Guy")
        board_row = (
            (await session.execute(select(BoardPlayer).where(BoardPlayer.name == "Some Guy")))
            .scalars()
            .one()
        )
    assert override_row.espn_player_id == 999
    assert board_row.match_method == "override"
    assert board_row.match_confidence == 1.0


@pytest.mark.asyncio
async def test_set_override_with_null_id_records_explicit_no_match(session_factory) -> None:
    await seed(session_factory, [_player("Some Guy", position="RB")])

    async with session_factory() as session:
        updated = await draft_matches.set_override(session, "Some Guy", None)

    assert updated.espn_player_id is None
    assert updated.match_method == "override"
    assert updated.match_confidence == 1.0


@pytest.mark.asyncio
async def test_set_override_unknown_name_returns_none(session_factory) -> None:
    async with session_factory() as session:
        result = await draft_matches.set_override(session, "Nobody Here", 1)
    assert result is None


@pytest.mark.asyncio
async def test_set_override_updates_an_existing_override_row_rather_than_duplicating(
    session_factory,
) -> None:
    await seed(session_factory, [_player("Some Guy", position="RB")])

    async with session_factory() as session:
        await draft_matches.set_override(session, "Some Guy", 111)
    async with session_factory() as session:
        await draft_matches.set_override(session, "Some Guy", 222)

    async with session_factory() as session:
        rows = (await session.execute(select(BoardIdOverride))).scalars().all()
    assert len(rows) == 1
    assert rows[0].espn_player_id == 222
