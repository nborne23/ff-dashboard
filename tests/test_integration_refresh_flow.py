"""Task 10.8 — end-to-end integration test through the real FastAPI app: a respx-mocked
Yahoo refresh populates SQLite, `GET /api/teams` serves a schema-valid envelope built
entirely from those persisted rows, and the SSE bus carries a `data.changed` event for
the "teams" scope for that same run — the three halves of the live-updates story
(write path, read path, push signal) exercised together instead of in isolation."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron import schemas
from backend.gridiron.config import get_settings
from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, Connection
from backend.gridiron.platforms.yahoo.client import BASE_URL as YAHOO_BASE
from backend.gridiron.schemas.events import DataChangedEvent
from backend.gridiron.services import credentials, differ, events, fantasy_service, live_state
from backend.gridiron.services.fantasy_service import TeamsData
from backend.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"

LEAGUE_ID = "yahoo:461.l.123456"
USER_TEAM = "yahoo:461.l.123456.t.1"


def load_fixture(platform: str, name: str) -> dict:
    return json.loads((FIXTURES / platform / name).read_text())


def _single_league_yahoo_leagues() -> dict:
    raw = load_fixture("yahoo", "leagues.json")
    leagues = raw["fantasy_content"]["users"]["0"]["user"][1]["games"]["0"]["game"][1]["leagues"]
    del leagues["1"]
    leagues["count"] = 1
    return raw


def _mock_yahoo_refresh() -> None:
    roster = load_fixture("yahoo", "roster.json")
    opp_roster = json.loads(json.dumps(roster).replace(".t.1", ".t.2"))
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_codes=nfl").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "games.json"))
    )
    respx.get(f"{YAHOO_BASE}/users;use_login=1/games;game_keys=461/leagues").mock(
        return_value=httpx.Response(200, json=_single_league_yahoo_leagues())
    )
    respx.get(f"{YAHOO_BASE}/league/461.l.123456/teams").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "teams.json"))
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.1/roster;week=14/players/stats").mock(
        return_value=httpx.Response(200, json=roster)
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.1/matchups;weeks=14").mock(
        return_value=httpx.Response(200, json=load_fixture("yahoo", "matchup.json"))
    )
    respx.get(f"{YAHOO_BASE}/team/461.l.123456.t.2/roster;week=14/players/stats").mock(
        return_value=httpx.Response(200, json=opp_roster)
    )


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    live_state.reset_state()
    differ.reset_state()
    events.reset()
    yield
    fantasy_service.reset_state()
    live_state.reset_state()
    differ.reset_state()
    events.reset()


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "integration.db")
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


async def _connect_yahoo(db) -> None:
    # `POST /api/admin/refresh` runs through the real (cached) `get_settings()`, so the
    # stored tokens must be encrypted with that exact process-wide secret — not a
    # test-local one — for `refresh_discovery` to be able to decrypt them again.
    secret = get_settings().gridiron_secret_key
    async with db() as session:
        session.add(
            Connection(
                platform="yahoo",
                access_token_enc=credentials.encrypt(secret, "at"),
                refresh_token_enc=credentials.encrypt(secret, "rt"),
            )
        )
        await session.commit()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_populates_db_teams_envelope_validates_and_publishes_data_changed(
    client, db
) -> None:
    await _connect_yahoo(db)
    _mock_yahoo_refresh()

    # Subscribe to the SSE bus *before* triggering the refresh so nothing published
    # during it is missed (mirrors how a real long-lived `/api/events` client would
    # already be connected before a scheduled run fires).
    queue = events.subscribe()

    refresh_response = await client.post("/api/admin/refresh?job=refresh_fantasy")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["ok"] is True

    # --- read path: GET /api/teams serves a schema-valid envelope from what the write
    # path just persisted -----------------------------------------------------------
    teams_response = await client.get("/api/teams?week=14")
    assert teams_response.status_code == 200
    body = teams_response.json()

    envelope = schemas.Envelope[TeamsData].model_validate(body)
    assert len(envelope.data.teams) == 1
    assert envelope.data.teams[0].id == USER_TEAM
    assert envelope.meta.platforms["yahoo"].ok is True

    # --- push signal: the same run published data.changed for the "teams" scope ----
    event = await asyncio.wait_for(queue.get(), timeout=2)
    assert isinstance(event, DataChangedEvent)
    assert "teams" in event.scopes


@pytest.mark.asyncio
@respx.mock
async def test_second_identical_refresh_publishes_no_further_data_changed(client, db) -> None:
    """The differ only publishes when something actually moved (task 8.4) -- exercised
    here through the real API + scheduler path, not just fantasy_service directly."""
    await _connect_yahoo(db)
    _mock_yahoo_refresh()

    first = await client.post("/api/admin/refresh?job=refresh_fantasy")
    assert first.json()["ok"] is True

    queue = events.subscribe()
    second = await client.post("/api/admin/refresh?job=refresh_fantasy")
    assert second.json()["ok"] is True

    assert queue.empty()
