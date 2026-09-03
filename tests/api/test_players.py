"""`GET /api/players/{player_id}/injury` — envelope, cache-only reads, and the three
"no report" cases the panel has to tell apart."""

from collections.abc import AsyncIterator
from datetime import datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, League, Player, PlayerInjury
from backend.gridiron.services import fantasy_service
from backend.main import app

CACHE_CONTROL = "private, max-age=60, stale-while-revalidate=120"


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "players-api.db")
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
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=2026,
                team_count=10,
                scoring_type="ppr",
                current_week=1,
            )
        )
        for player_id, platform, status in [
            ("espn:p-4428209", "espn", "IR"),
            ("espn:p-100", "espn", "ACTIVE"),
            ("yahoo:p-30123", "yahoo", "Q"),
        ]:
            session.add(
                Player(
                    id=player_id,
                    platform=platform,
                    platform_id=player_id.split(":")[1],
                    name="Player",
                    position="WR",
                    nfl_team="SF",
                    injury_status=status,
                )
            )
        session.add(
            PlayerInjury(
                player_id="espn:p-4428209",
                report_id="633398",
                status="Injured Reserve",
                injury_type="Knee - PCL",
                location="Leg",
                detail="Surgery",
                side="Right",
                return_date="2027-02-15",
                short_comment="Season-ending surgery.",
                long_comment="6-to-12 month recovery.",
                reported_at=datetime(2026, 8, 13, 15, 11),
                fetched_at=datetime(2026, 9, 2, 12, 0),
            )
        )
        await session.commit()


async def test_returns_the_stored_report_in_an_envelope(client, db):
    await seed(db)
    response = await client.get("/api/players/espn:p-4428209/injury")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == CACHE_CONTROL

    body = response.json()
    assert set(body) == {"data", "meta"}
    data = body["data"]
    assert data["injury_status"] == "IR"
    assert data["detail_supported"] is True
    assert data["report"]["injury_type"] == "Knee - PCL"
    assert data["report"]["side"] == "Right"
    assert data["report"]["return_date"] == "2027-02-15"


async def test_healthy_player_is_a_200_with_a_null_report(client, db):
    """ "Nothing on file" is the common answer and must not read as an error."""
    await seed(db)
    response = await client.get("/api/players/espn:p-100/injury")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "player_id": "espn:p-100",
        "injury_status": "ACTIVE",
        "report": None,
        "detail_supported": True,
    }


async def test_yahoo_player_reports_detail_unsupported(client, db):
    """The badge still renders from the platform status; only the DETAIL is unavailable,
    and the panel needs to say which of the two it is."""
    await seed(db)
    data = (await client.get("/api/players/yahoo:p-30123/injury")).json()["data"]
    assert data["injury_status"] == "Q"
    assert data["report"] is None
    assert data["detail_supported"] is False


async def test_unknown_player_is_a_typed_404(client, db):
    await seed(db)
    response = await client.get("/api/players/espn:p-999/injury")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "player_not_found"
