"""`DELETE /api/cache` + `GET /api/export.json` — Settings' "Data Management" card (7.7)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, HttpCache, League, Matchup, Player, RosterSlot, Team
from backend.gridiron.services import cache as cache_service
from backend.main import app

LEAGUE_ID = "yahoo:461.l.123456"
TEAM_ID = "yahoo:461.l.123456.t.1"


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "data-api.db")
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


# --- DELETE /api/cache -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_cache_deletes_all_rows(client, db) -> None:
    async with db() as session:
        await cache_service.set(
            session,
            "yahoo",
            "roster",
            {"week": 14},
            "{}",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await cache_service.set(
            session, "espn", "league", None, "{}", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )

    response = await client.delete("/api/cache")

    assert response.status_code == 204

    async with db() as session:
        rows = (await session.execute(select(HttpCache))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_clear_cache_on_empty_cache_is_a_noop(client) -> None:
    response = await client.delete("/api/cache")
    assert response.status_code == 204


# --- GET /api/export.json ---------------------------------------------------------------


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
                id=TEAM_ID,
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
            Player(
                id="yahoo:461.p.1",
                platform="yahoo",
                platform_id="461.p.1",
                name="Patrick Mahomes",
                position="QB",
                nfl_team="KC",
            )
        )
        session.add(
            RosterSlot(
                team_id=TEAM_ID,
                week=14,
                slot="QB",
                player_id="yahoo:461.p.1",
                proj_points=22.1,
                actual_points=27.4,
            )
        )
        session.add(
            Matchup(
                id="yahoo:461.l.123456.mu.14",
                league_id=LEAGUE_ID,
                week=14,
                home_team_id=TEAM_ID,
                away_team_id=TEAM_ID,
                home_score=88.24,
                away_score=76.10,
                home_proj=104.5,
                away_proj=95.2,
                is_complete=False,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_export_returns_every_table_and_download_headers(client, db) -> None:
    await seed(db)

    response = await client.get("/api/export.json")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == "attachment; filename=gridiron-export.json"
    body = response.json()
    assert set(body) == {
        "exported_at",
        "leagues",
        "teams",
        "players",
        "roster_slots",
        "matchups",
        "season_weeks",
    }
    assert len(body["leagues"]) == 1
    assert body["leagues"][0]["id"] == LEAGUE_ID
    assert len(body["teams"]) == 1
    assert body["teams"][0]["id"] == TEAM_ID
    assert len(body["players"]) == 1
    assert len(body["roster_slots"]) == 1
    assert body["roster_slots"][0]["actual_points"] == 27.4
    assert len(body["matchups"]) == 1
    assert body["season_weeks"] == []


@pytest.mark.asyncio
async def test_export_empty_db_returns_empty_lists(client) -> None:
    response = await client.get("/api/export.json")

    assert response.status_code == 200
    body = response.json()
    assert body["leagues"] == []
    assert body["teams"] == []
