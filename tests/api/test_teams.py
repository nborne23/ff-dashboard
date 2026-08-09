"""`/api/teams*` — envelope shape, Cache-Control headers, 404 typed errors, week defaulting."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, League, Matchup, MatchupSlot, Player, SeasonWeek, Team
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
