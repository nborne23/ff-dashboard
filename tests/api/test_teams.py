"""`/api/teams*` — envelope shape, Cache-Control headers, 404 typed errors, week defaulting."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import (
    Base,
    League,
    Matchup,
    MatchupSlot,
    Player,
    PlayerPoolEntry,
    RosterSlot,
    SeasonWeek,
    Team,
)
from backend.gridiron.services import fantasy_service
from backend.main import app

CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"

LEAGUE_ID = "yahoo:461.l.123456"
USER_TEAM = "yahoo:461.l.123456.t.1"
OPP_TEAM = "yahoo:461.l.123456.t.2"


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "teams-api.db")
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


async def seed(db) -> None:
    async with db() as session:
        session.add(
            League(
                id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456",
                name="The League",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=14,
            )
        )
        session.add(
            Team(
                id=USER_TEAM,
                league_id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456.t.1",
                name="Gridiron Gurus",
                manager_name="Nick",
                record_w=8,
                record_l=5,
                record_t=0,
                rank_current=2,
                rank_total=10,
                points_for=1401.2,
                points_against=1322.8,
                is_user_team=True,
            )
        )
        session.add(
            Team(
                id=OPP_TEAM,
                league_id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456.t.2",
                name="The Contenders",
                manager_name="Sam",
                record_w=7,
                record_l=6,
                record_t=0,
                rank_current=4,
                rank_total=10,
                points_for=1350.0,
                points_against=1360.0,
                is_user_team=False,
            )
        )
        session.add_all(
            [
                Player(
                    id="yahoo:461.p.1",
                    platform="yahoo",
                    platform_id="461.p.1",
                    name="Patrick Mahomes",
                    position="QB",
                    nfl_team="KC",
                ),
                Player(
                    id="yahoo:461.p.4",
                    platform="yahoo",
                    platform_id="461.p.4",
                    name="Josh Allen",
                    position="QB",
                    nfl_team="BUF",
                ),
            ]
        )
        matchup = Matchup(
            id="yahoo:461.l.123456.mu.14",
            league_id=LEAGUE_ID,
            week=14,
            home_team_id=USER_TEAM,
            away_team_id=OPP_TEAM,
            home_score=88.24,
            away_score=76.10,
            home_proj=104.5,
            away_proj=95.2,
            is_complete=False,
        )
        session.add(matchup)
        session.add(
            MatchupSlot(
                matchup_id=matchup.id,
                slot="QB",
                home_player_id="yahoo:461.p.1",
                away_player_id="yahoo:461.p.4",
                home_pts=27.4,
                away_pts=24.5,
            )
        )
        session.add(
            SeasonWeek(
                team_id=USER_TEAM,
                week=14,
                score=88.24,
                opp_score=76.10,
                opp_team_name="The Contenders",
                is_win=False,
                is_current=True,
            )
        )
        await session.commit()


def assert_envelope(body: dict) -> None:
    assert set(body) == {"data", "meta"}
    meta = body["meta"]
    assert meta["live_state"] in ("live", "game_day", "off_day")
    assert meta["as_of"] is not None
    assert meta["next_refresh_at"] is not None
    assert set(meta["platforms"]) == {"yahoo", "espn"}
    for status in meta["platforms"].values():
        assert "ok" in status


@pytest.mark.asyncio
async def test_list_teams_empty_db_returns_envelope_not_500(client) -> None:
    response = await client.get("/api/teams")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert body["data"] == {"teams": []}
    assert body["meta"]["platforms"]["yahoo"] == {"ok": False, "error": "not_connected"}
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_list_teams_returns_user_teams_for_default_week(client, db) -> None:
    await seed(db)

    response = await client.get("/api/teams")  # week defaults to League.current_week (14)

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    teams = body["data"]["teams"]
    assert len(teams) == 1
    team = teams[0]
    assert team["id"] == USER_TEAM
    assert team["record"] == {"w": 8, "l": 5, "t": 0}
    assert team["rank"] == {"current": 2, "total": 10}
    assert team["current_score"] == 88.24
    assert team["current_opponent_name"] == "The Contenders"
    assert team["accent_color"] == "#FF2D55"


@pytest.mark.asyncio
async def test_get_team_detail_shape(client, db) -> None:
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}?week=14")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"team", "league", "starters", "bench", "record_history"}
    assert data["team"]["id"] == USER_TEAM
    assert data["league"]["id"] == LEAGUE_ID
    assert data["record_history"][0]["week"] == 14
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_get_team_unknown_id_returns_typed_404(client, db) -> None:
    await seed(db)

    response = await client.get("/api/teams/yahoo:nope")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "team_not_found"
    assert "yahoo:nope" in detail["message"]


@pytest.mark.asyncio
async def test_get_h2h_shape(client, db) -> None:
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/h2h?week=14")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"matchup", "slots", "remaining"}
    assert data["matchup"]["home_team_id"] == USER_TEAM
    assert data["slots"][0]["home_player"]["name"] == "Patrick Mahomes"
    assert data["remaining"] == {"mine": 0, "theirs": 0}  # no roster rows seeded
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_get_h2h_missing_matchup_returns_typed_404(client, db) -> None:
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/h2h?week=3")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "matchup_not_found"


@pytest.mark.asyncio
async def test_get_season_shape(client, db) -> None:
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/season")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"weeks", "highlights"}
    assert set(data["highlights"]) == {"season_high", "win_streak", "most_started"}
    assert data["weeks"][0]["week"] == 14
    assert data["highlights"]["season_high"]["score"] == 88.24
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_get_day_rings_shape(client, db) -> None:
    await seed(db)

    response = await client.get("/api/teams/day-rings?week=14")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"days", "today_index"}
    assert len(data["days"]) == 5
    assert [d["letter"] for d in data["days"]] == ["T", "F", "S", "S", "M"]
    for day in data["days"]:
        assert len(day["rings"]) == 1  # one seeded user team
        assert set(day["rings"][0]) == {"value", "color"}
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_get_day_rings_empty_db_returns_no_rings_not_500(client) -> None:
    response = await client.get("/api/teams/day-rings")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert len(body["data"]["days"]) == 5
    assert all(day["rings"] == [] for day in body["data"]["days"])


@pytest.mark.asyncio
async def test_day_rings_route_is_not_swallowed_by_the_team_id_route(client, db) -> None:
    """Registration-order regression guard (task 10.6): `/day-rings` must resolve to the
    dedicated endpoint, not `get_team` with team_id="day-rings" (which would 404)."""
    await seed(db)

    response = await client.get("/api/teams/day-rings")

    assert response.status_code == 200
    assert "days" in response.json()["data"]


@pytest.mark.asyncio
async def test_get_season_unknown_team_returns_typed_404(client) -> None:
    response = await client.get("/api/teams/yahoo:nope/season")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "team_not_found"


# --------------------------------------------------------------------------------------
# /api/teams/game-day — the bulk Game Day envelope (add-game-day-view, tasks 7.1–7.2)
# --------------------------------------------------------------------------------------


async def seed_game_day_extras(db) -> None:
    """A second league on the other platform where the user is the AWAY side, plus the
    roster_slots rows that carry per-side live state.

    ESPN labels the QB slot `QB` and the flex `FLEX` while this league's Yahoo matchup
    slots are built by `_pair_matchup_slots` from the same labels — the point of the
    seed is that the *state* still resolves per (team, player), so a slot-label join
    would be the only thing that could get it wrong.
    """
    async with db() as session:
        session.add(
            League(
                id="espn:l-999",
                platform="espn",
                platform_id="999",
                name="ESPN Keeper",
                season=2025,
                team_count=12,
                scoring_type="ppr",
                current_week=14,
            )
        )
        session.add(
            Team(
                id="espn:l-999-t-7",
                league_id="espn:l-999",
                platform="espn",
                platform_id="l-999-t-7",
                name="Away Siders",
                manager_name="Nick",
                record_w=6,
                record_l=7,
                record_t=0,
                rank_current=9,
                rank_total=12,
                points_for=1200.0,
                points_against=1250.0,
                is_user_team=True,
            )
        )
        session.add(
            Team(
                id="espn:l-999-t-3",
                league_id="espn:l-999",
                platform="espn",
                platform_id="l-999-t-3",
                name="Home Siders",
                manager_name="Riley",
                record_w=10,
                record_l=3,
                record_t=0,
                rank_current=1,
                rank_total=12,
                points_for=1500.0,
                points_against=1100.0,
                is_user_team=False,
            )
        )
        session.add_all(
            [
                Player(
                    id="espn:p-50",
                    platform="espn",
                    platform_id="50",
                    name="Bijan Robinson",
                    position="RB",
                    nfl_team="ATL",
                ),
                Player(
                    id="espn:p-51",
                    platform="espn",
                    platform_id="51",
                    name="Saquon Barkley",
                    position="RB",
                    nfl_team="PHI",
                ),
            ]
        )
        espn_matchup = Matchup(
            id="espn:l-999-m-4-w-14",
            league_id="espn:l-999",
            week=14,
            home_team_id="espn:l-999-t-3",
            away_team_id="espn:l-999-t-7",  # the user is AWAY here
            home_score=110.0,
            away_score=95.5,
            home_proj=130.0,
            away_proj=118.0,
            is_complete=True,
        )
        session.add(espn_matchup)
        session.add(
            MatchupSlot(
                matchup_id=espn_matchup.id,
                slot="RB1",
                home_player_id="espn:p-50",
                away_player_id="espn:p-51",
                home_pts=18.4,
                away_pts=22.1,
            )
        )
        # Per-side live state lives only on roster_slots — matchup_slots persists points.
        session.add_all(
            [
                RosterSlot(
                    team_id="espn:l-999-t-3",
                    week=14,
                    slot="RB1",
                    player_id="espn:p-50",
                    proj_points=17.0,
                    actual_points=18.4,
                    is_live=False,
                    game_state="post",
                ),
                RosterSlot(
                    team_id="espn:l-999-t-7",
                    week=14,
                    slot="FLEX",  # deliberately a DIFFERENT label than the matchup slot
                    player_id="espn:p-51",
                    proj_points=19.5,
                    actual_points=22.1,
                    is_live=True,
                    game_state="in",
                ),
                # The Yahoo league's two QBs, one live and one not yet kicked off.
                RosterSlot(
                    team_id=USER_TEAM,
                    week=14,
                    slot="QB",
                    player_id="yahoo:461.p.1",
                    proj_points=25.0,
                    actual_points=27.4,
                    is_live=True,
                    game_state="in",
                ),
                RosterSlot(
                    team_id=OPP_TEAM,
                    week=14,
                    slot="QB",
                    player_id="yahoo:461.p.4",
                    proj_points=23.0,
                    actual_points=24.5,
                    is_live=False,
                    game_state="pre",
                ),
            ]
        )
        await session.commit()


def game_day_entry(body: dict, team_id: str) -> dict:
    return next(m for m in body["data"]["matchups"] if m["team_id"] == team_id)


@pytest.mark.asyncio
async def test_game_day_route_is_not_swallowed_by_the_team_id_route(client, db) -> None:
    """Registration-order guard: `/game-day` must reach the bulk handler, not `get_team`
    with team_id="game-day" (which would 404 as an unknown team)."""
    await seed(db)

    response = await client.get("/api/teams/game-day")

    assert response.status_code == 200
    assert "matchups" in response.json()["data"]


@pytest.mark.asyncio
async def test_game_day_empty_db_returns_empty_matchups_not_an_error(client) -> None:
    response = await client.get("/api/teams/game-day")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert body["data"] == {"matchups": []}
    assert response.headers["Cache-Control"] == CACHE_CONTROL


@pytest.mark.asyncio
async def test_game_day_envelope_shape_and_week_defaulting(client, db) -> None:
    await seed(db)
    await seed_game_day_extras(db)

    # No `week` param — resolves to the leagues' current_week (14), the same way the
    # other team endpoints do.
    response = await client.get("/api/teams/game-day")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    matchups = body["data"]["matchups"]
    assert len(matchups) == 2  # one per user team

    entry = game_day_entry(body, USER_TEAM)
    assert set(entry) == {
        "team_id",
        "team_name",
        "opp_team_id",
        "opp_team_name",
        "league_id",
        "league_name",
        "platform",
        "team_logo_url",
        "opp_logo_url",
        "record",
        "rank",
        "score",
        "opp_score",
        "proj",
        "opp_proj",
        "remaining",
        "is_complete",
        "i_am_home",
        "slots",
    }
    assert entry["team_name"] == "Gridiron Gurus"
    assert entry["opp_team_id"] == OPP_TEAM
    assert entry["opp_team_name"] == "The Contenders"
    assert entry["league_name"] == "The League"
    # Derived from the id prefix — Team carries no platform field (design D5).
    assert entry["platform"] == "yahoo"
    assert entry["record"] == {"w": 8, "l": 5, "t": 0}
    assert entry["rank"] == {"current": 2, "total": 10}
    assert entry["score"] == pytest.approx(88.24)
    assert entry["opp_score"] == pytest.approx(76.10)
    assert entry["proj"] == pytest.approx(104.5)
    assert entry["opp_proj"] == pytest.approx(95.2)
    assert entry["is_complete"] is False
    assert entry["i_am_home"] is True
    # No win_prob on the envelope (design D7) — one implementation, client-side.
    assert "win_prob" not in entry


@pytest.mark.asyncio
async def test_game_day_orients_an_away_side_user_team_onto_its_own_perspective(client, db) -> None:
    await seed(db)
    await seed_game_day_extras(db)

    body = (await client.get("/api/teams/game-day?week=14")).json()
    entry = game_day_entry(body, "espn:l-999-t-7")

    # The user is the AWAY side of this matchup; the entry still reports them as the
    # subject, so the consumer never re-derives home/away.
    assert entry["team_name"] == "Away Siders"
    assert entry["score"] == pytest.approx(95.5)
    assert entry["opp_team_id"] == "espn:l-999-t-3"
    assert entry["opp_team_name"] == "Home Siders"
    assert entry["opp_score"] == pytest.approx(110.0)
    assert entry["proj"] == pytest.approx(118.0)
    assert entry["opp_proj"] == pytest.approx(130.0)
    assert entry["platform"] == "espn"
    assert entry["is_complete"] is True
    # The slots keep the raw home/away shape, so the client needs this to orient them.
    assert entry["i_am_home"] is False


@pytest.mark.asyncio
async def test_game_day_remaining_counts_unfinished_starters_per_side(client, db) -> None:
    await seed(db)
    await seed_game_day_extras(db)

    body = (await client.get("/api/teams/game-day?week=14")).json()
    entry = game_day_entry(body, USER_TEAM)

    # The user's QB is `in` (not finished) and the opponent's is `pre` — both remaining.
    assert entry["remaining"] == {"mine": 1, "theirs": 1}


@pytest.mark.asyncio
async def test_game_day_past_week_reports_that_weeks_scores_not_the_current_weeks(
    client, db
) -> None:
    """Task 7.1b: team-level score fields derive from the *requested* week's matchups
    row, so a past-week request never mixes past slots with present scores."""
    await seed(db)
    async with db() as session:
        session.add(
            Team(
                id="yahoo:461.l.123456.t.3",
                league_id=LEAGUE_ID,
                platform="yahoo",
                platform_id="461.l.123456.t.3",
                name="Week Three Foe",
                manager_name="Alex",
                record_w=1,
                record_l=2,
                record_t=0,
                rank_current=8,
                rank_total=10,
                points_for=300.0,
                points_against=330.0,
                is_user_team=False,
            )
        )
        session.add(
            Matchup(
                id="yahoo:461.l.123456.mu.3",
                league_id=LEAGUE_ID,
                week=3,
                home_team_id=USER_TEAM,
                away_team_id="yahoo:461.l.123456.t.3",
                home_score=101.5,
                away_score=99.25,
                home_proj=100.0,
                away_proj=98.0,
                is_complete=True,
            )
        )
        await session.commit()

    body = (await client.get("/api/teams/game-day?week=3")).json()
    entry = game_day_entry(body, USER_TEAM)

    assert entry["score"] == pytest.approx(101.5)
    assert entry["opp_score"] == pytest.approx(99.25)
    assert entry["opp_team_name"] == "Week Three Foe"
    assert entry["is_complete"] is True
    # Not week 14's values, which the same team also has.
    assert entry["score"] != pytest.approx(88.24)


@pytest.mark.asyncio
async def test_matchup_slot_per_side_state_matches_the_roster_slot_rows(client, db) -> None:
    """Task 7.2: per-side state is joined on player identity, scoped to that side's own
    team. The ESPN league's matchup slot is labelled `RB1` while the away team's roster
    row for the same player is labelled `FLEX` — a slot-label join would find nothing
    (or the wrong row), so this is the guard on the 2.1 join key."""
    await seed(db)
    await seed_game_day_extras(db)

    body = (await client.get("/api/teams/game-day?week=14")).json()

    espn_slot = game_day_entry(body, "espn:l-999-t-7")["slots"][0]
    assert espn_slot["slot"] == "RB1"
    # Home side: `post`, not live (labels agree here).
    assert espn_slot["home_state"] == "post"
    assert espn_slot["home_is_live"] is False
    # Away side: the roster row is labelled FLEX, yet the state still resolves.
    assert espn_slot["away_state"] == "in"
    assert espn_slot["away_is_live"] is True

    yahoo_slot = game_day_entry(body, USER_TEAM)["slots"][0]
    assert yahoo_slot["home_state"] == "in"
    assert yahoo_slot["home_is_live"] is True
    assert yahoo_slot["away_state"] == "pre"
    assert yahoo_slot["away_is_live"] is False


@pytest.mark.asyncio
async def test_h2h_carries_the_same_per_side_state(client, db) -> None:
    """The four new MatchupSlot fields are populated on `/h2h` too, not just the bulk
    endpoint — they are part of the schema, not of one response shape."""
    await seed(db)
    await seed_game_day_extras(db)

    body = (await client.get(f"/api/teams/{USER_TEAM}/h2h?week=14")).json()
    slot = body["data"]["slots"][0]

    assert slot["home_state"] == "in"
    assert slot["home_is_live"] is True
    assert slot["away_state"] == "pre"
    assert slot["away_is_live"] is False


@pytest.mark.asyncio
async def test_matchup_slot_state_defaults_when_no_roster_row_exists(client, db) -> None:
    """`seed()` writes matchup slots but no roster_slots. An unmatched player is
    unclassified (null state) and not live — never an invented `post`."""
    await seed(db)

    body = (await client.get("/api/teams/game-day?week=14")).json()
    slot = game_day_entry(body, USER_TEAM)["slots"][0]

    assert slot["home_state"] is None
    assert slot["away_state"] is None
    assert slot["home_is_live"] is False
    assert slot["away_is_live"] is False


@pytest.mark.asyncio
async def test_game_day_query_count_does_not_grow_with_team_count(db) -> None:
    """Task 2.4 / the spec's "No N+1" scenario: the query count is bounded regardless of
    how many user teams there are. Counted at the SQLAlchemy engine level so the
    assertion is about real round-trips, not about how the code is shaped."""
    from sqlalchemy import event

    await seed(db)
    await seed_game_day_extras(db)

    async with db() as session:
        # `session.get_bind()` on an AsyncSession hands back the underlying *sync*
        # Engine, which is what carries the DBAPI-level events.
        sync_engine = session.get_bind().engine
        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(sync_engine, "before_cursor_execute", record)
        try:
            two_team_data = await fantasy_service.game_day(session, 14)
            two_team_queries = len(statements)
            statements.clear()

            # A third user team in a third league — one more matchup, one more panel.
            session.add(
                League(
                    id="espn:l-777",
                    platform="espn",
                    platform_id="777",
                    name="Third League",
                    season=2025,
                    team_count=8,
                    scoring_type="ppr",
                    current_week=14,
                )
            )
            session.add_all(
                [
                    Team(
                        id="espn:l-777-t-1",
                        league_id="espn:l-777",
                        platform="espn",
                        platform_id="l-777-t-1",
                        name="Third Team",
                        manager_name="Nick",
                        record_w=5,
                        record_l=8,
                        record_t=0,
                        rank_current=7,
                        rank_total=8,
                        points_for=1000.0,
                        points_against=1100.0,
                        is_user_team=True,
                    ),
                    Team(
                        id="espn:l-777-t-2",
                        league_id="espn:l-777",
                        platform="espn",
                        platform_id="l-777-t-2",
                        name="Third Foe",
                        manager_name="Jo",
                        record_w=8,
                        record_l=5,
                        record_t=0,
                        rank_current=2,
                        rank_total=8,
                        points_for=1150.0,
                        points_against=1000.0,
                        is_user_team=False,
                    ),
                ]
            )
            session.add(
                Matchup(
                    id="espn:l-777-m-1-w-14",
                    league_id="espn:l-777",
                    week=14,
                    home_team_id="espn:l-777-t-1",
                    away_team_id="espn:l-777-t-2",
                    home_score=70.0,
                    away_score=65.0,
                    home_proj=105.0,
                    away_proj=100.0,
                    is_complete=False,
                )
            )
            await session.commit()
            statements.clear()

            three_team_data = await fantasy_service.game_day(session, 14)
            three_team_queries = len(statements)
        finally:
            event.remove(sync_engine, "before_cursor_execute", record)

    assert len(two_team_data.matchups) == 2
    assert len(three_team_data.matchups) == 3
    assert three_team_queries == two_team_queries


@pytest.mark.asyncio
async def test_game_day_excludes_disabled_leagues(client, db) -> None:
    """A league switched off in Settings must not reappear on Game Day. Discovery leaves
    a disabled league's rows in place rather than deleting them, so the filter has to be
    applied on every read — the same way `list_teams` and `day_rings` do it."""
    await seed(db)
    await seed_game_day_extras(db)

    before = (await client.get("/api/teams/game-day?week=14")).json()
    assert len(before["data"]["matchups"]) == 2

    async with db() as session:
        league = await session.get(League, "espn:l-999")
        league.is_enabled = False
        await session.commit()

    after = (await client.get("/api/teams/game-day?week=14")).json()
    team_ids = [m["team_id"] for m in after["data"]["matchups"]]

    assert team_ids == [USER_TEAM]
    assert "espn:l-999-t-7" not in team_ids


# ---------------------------------------------------------------------------
# /api/teams/{team_id}/waivers (add-player-pool group 4)
# ---------------------------------------------------------------------------

WAIVER_TEAM = "yahoo:461.l.123456.t.1"


async def _seed_waiver_pool(db) -> None:
    """A pool for the already-seeded league: one starter to compare against, and two
    candidates straddling that starter's projection."""
    async with db() as session:
        session.add(
            RosterSlot(
                team_id=USER_TEAM,
                week=14,
                slot="RB1",
                player_id="yahoo:461.p.100",
                proj_points=9.0,
                actual_points=0.0,
                is_live=False,
                game_state=None,
                status_text="",
            )
        )
        for pid, name, pos in (
            ("yahoo:461.p.100", "Incumbent RB", "RB"),
            ("yahoo:461.p.200", "Upgrade RB", "RB"),
            ("yahoo:461.p.201", "Downgrade RB", "RB"),
        ):
            session.add(
                Player(
                    id=pid,
                    platform="yahoo",
                    platform_id=pid.split(":")[1],
                    name=name,
                    position=pos,
                    nfl_team="DET",
                    nfl_opponent=None,
                    nfl_game_id=None,
                    bye_week=5,
                    injury_status="ACTIVE",
                )
            )
        eligible = json.dumps(["RB", "RB/WR", "FLEX", "BN", "IR"])
        session.add(
            PlayerPoolEntry(
                league_id=LEAGUE_ID,
                player_id="yahoo:461.p.100",
                status="ONTEAM",
                on_team_id="1",
                percent_owned=95.0,
                percent_started=90.0,
                season_proj_points=153.0,
                eligible_slots=eligible,
            )
        )
        session.add(
            PlayerPoolEntry(
                league_id=LEAGUE_ID,
                player_id="yahoo:461.p.200",
                status="FREEAGENT",
                on_team_id=None,
                percent_owned=30.0,
                percent_started=5.0,
                season_proj_points=200.0,
                eligible_slots=eligible,
            )
        )
        session.add(
            PlayerPoolEntry(
                league_id=LEAGUE_ID,
                player_id="yahoo:461.p.201",
                status="WAIVERS",
                on_team_id=None,
                percent_owned=10.0,
                percent_started=1.0,
                season_proj_points=None,
                eligible_slots=eligible,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_waivers_shape(client, db) -> None:
    await seed(db)
    await _seed_waiver_pool(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/waivers?week=14")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"team_id", "league_id", "week", "candidates"}
    assert data["team_id"] == USER_TEAM
    assert response.headers["Cache-Control"] == CACHE_CONTROL

    names = [c["player"]["name"] for c in data["candidates"]]
    assert names == ["Upgrade RB", "Downgrade RB"]  # projection desc, nulls last
    assert "Incumbent RB" not in names  # ONTEAM is never claimable

    upgrade = data["candidates"][0]
    assert upgrade["delta_vs_worst_starter"] == pytest.approx(47.0)  # 200.0 - 153.0

    # A missing value must serialize as null, never 0 — the UI renders an em dash.
    downgrade = data["candidates"][1]
    assert downgrade["season_proj_points"] is None
    assert downgrade["delta_vs_worst_starter"] is None


@pytest.mark.asyncio
async def test_get_waivers_position_filter(client, db) -> None:
    await seed(db)
    await _seed_waiver_pool(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/waivers?week=14&position=WR")

    assert response.status_code == 200
    assert response.json()["data"]["candidates"] == []


@pytest.mark.asyncio
async def test_get_waivers_unknown_team_returns_typed_404(client, db) -> None:
    await seed(db)

    response = await client.get("/api/teams/yahoo:nope/waivers?week=14")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "team_not_found"


@pytest.mark.asyncio
async def test_get_waivers_empty_pool_returns_an_empty_list(client, db) -> None:
    """A league whose pool has never synced is empty, not broken."""
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/waivers?week=14")

    assert response.status_code == 200
    assert response.json()["data"]["candidates"] == []


@pytest.mark.asyncio
async def test_get_waivers_defaults_the_week(client, db) -> None:
    await seed(db)
    await _seed_waiver_pool(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/waivers")

    assert response.status_code == 200
    assert response.json()["data"]["week"] == 14


# ---------------------------------------------------------------------------
# /api/teams/{team_id}/league (add-league-standings group 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_league_standings_shape(client, db) -> None:
    await seed(db)

    response = await client.get(f"/api/teams/{USER_TEAM}/league")

    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    data = body["data"]
    assert set(data) == {"league", "rows"}
    assert data["league"]["id"] == LEAGUE_ID
    assert response.headers["Cache-Control"] == CACHE_CONTROL

    names = [r["team"]["name"] for r in data["rows"]]
    assert "Gridiron Gurus" in names
    assert [r["position"] for r in data["rows"]] == list(range(1, len(data["rows"]) + 1))

    mine = [r for r in data["rows"] if r["team"]["is_user_team"]]
    assert len(mine) == 1


@pytest.mark.asyncio
async def test_get_league_standings_unknown_team_returns_typed_404(client, db) -> None:
    await seed(db)

    response = await client.get("/api/teams/yahoo:nope/league")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "team_not_found"


async def test_lineup_endpoint_returns_an_envelope(client, db):
    await seed(db)
    response = await client.get(f"/api/teams/{USER_TEAM}/lineup?week=14")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == CACHE_CONTROL

    data = response.json()["data"]
    assert data["team_id"] == USER_TEAM
    # Defaults to the independent source — it is the reason this endpoint can say
    # anything the league host's own app doesn't already.
    assert data["source"] == "rotowire"
    assert set(data) >= {
        "moves",
        "gain",
        "sources_agree",
        "comparison_available",
        "advice_available",
        "unevaluated",
    }


async def test_lineup_endpoint_accepts_the_platform_source(client, db):
    await seed(db)
    data = (await client.get(f"/api/teams/{USER_TEAM}/lineup?week=14&source=platform")).json()[
        "data"
    ]
    assert data["source"] == "platform"


async def test_lineup_endpoint_rejects_an_unknown_source(client, db):
    await seed(db)
    response = await client.get(f"/api/teams/{USER_TEAM}/lineup?week=14&source=espn")
    assert response.status_code == 422


async def test_lineup_endpoint_404s_an_unknown_team(client, db):
    await seed(db)
    response = await client.get("/api/teams/espn:l-9-t-9/lineup?week=14")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "team_not_found"
