"""The read-only MCP server: tools read the persisted model, errors reach the model, and
the endpoint is reachable only at the secret path."""

import json
from datetime import datetime

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron import mcp_server
from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, PlayerInjury, RosterSlot, Team
from backend.gridiron.services import fantasy_service

TEAM = "espn:l-1-t-1"
TOKEN = "t" * 32


@pytest.fixture(autouse=True)
def _reset_module_state():
    fantasy_service.reset_state()
    yield
    fantasy_service.reset_state()


@pytest.fixture
async def db(tmp_path, monkeypatch):
    engine = make_engine(tmp_path / "mcp.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(mcp_server, "async_session_factory", factory)
    async with factory() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=2026,
                team_count=10,
                scoring_type="ppr",
                current_week=3,
            )
        )
        session.add(
            Team(
                id=TEAM,
                league_id="espn:1",
                platform="espn",
                platform_id="l-1-t-1",
                name="Mine",
                manager_name="me",
                rank_current=1,
                rank_total=10,
                is_user_team=True,
            )
        )
        session.add(
            Player(
                id="espn:p-1",
                platform="espn",
                platform_id="p-1",
                name="Hurt Guy",
                position="WR",
                nfl_team="SF",
                injury_status="IR",
            )
        )
        session.add(
            PlayerInjury(
                player_id="espn:p-1",
                report_id="1",
                status="Injured Reserve",
                injury_type="Knee",
                short_comment="Out.",
                reported_at=datetime(2026, 9, 1),
                fetched_at=datetime(2026, 9, 2),
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


async def call(name: str, **args):
    result = await mcp_server.build_server().call_tool(name, args)
    return json.loads(result.content[0].text)


async def test_exposes_only_read_tools():
    names = {t.name for t in await mcp_server.build_server().list_tools()}
    assert names == {
        "list_teams",
        "game_day",
        "get_team",
        "get_matchup",
        "get_season",
        "get_league_standings",
        "get_waivers",
        "get_lineup_advice",
        "get_league_rosters",
        "get_player_injury",
    }


async def test_list_teams_defaults_to_the_current_week_and_drops_display_noise(db):
    data = await call("list_teams")
    assert data["week"] == 3
    assert [t["id"] for t in data["teams"]] == [TEAM]
    assert not {"logo_url", "accent_color", "spark_last_6"} & set(data["teams"][0])


async def test_unknown_team_is_a_tool_error_that_names_the_fix(db):
    with pytest.raises(ToolError, match="list_teams"):
        await mcp_server.build_server().call_tool("get_season", {"team_id": "espn:nope"})


async def test_player_injury_report(db):
    data = await call("get_player_injury", player_id="espn:p-1")
    assert data["injury_status"] == "IR"
    assert data["report"]["injury_type"] == "Knee"


async def test_player_without_a_report_is_null_not_an_error(db):
    async with db() as session:
        session.add(
            Player(
                id="espn:p-2",
                platform="espn",
                platform_id="p-2",
                name="Fine",
                position="RB",
                nfl_team="SF",
            )
        )
        await session.commit()
    assert (await call("get_player_injury", player_id="espn:p-2"))["report"] is None


def test_refuses_a_missing_or_short_token():
    for token in ("", "short"):
        with pytest.raises(RuntimeError, match="GRIDIRON_MCP_TOKEN"):
            mcp_server.create_app(token)


async def test_only_the_secret_path_serves_mcp(db):
    app = mcp_server.create_app(TOKEN)
    headers = {"Accept": "application/json, text/event-stream"}
    list_tools = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/healthz")).status_code == 200
            assert (
                await client.post("/mcp/wrong", json=list_tools, headers=headers)
            ).status_code == 404
            assert (await client.post("/mcp", json=list_tools, headers=headers)).status_code == 404
            ok = await client.post(f"/mcp/{TOKEN}", json=list_tools, headers=headers)
            assert ok.status_code == 200
            assert len(ok.json()["result"]["tools"]) == 10


async def test_the_connector_dialog_can_probe_the_endpoint_from_the_browser(db):
    """claude.ai checks the URL from the browser before saving the connector, so the
    endpoint has to answer a preflight and name the origin back."""
    app = mcp_server.create_app(TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            preflight = await client.request(
                "OPTIONS",
                f"/mcp/{TOKEN}",
                headers={
                    "Origin": "https://claude.ai",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "https://claude.ai"

            posted = await client.post(
                f"/mcp/{TOKEN}",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Origin": "https://claude.ai",
                },
            )
            assert posted.status_code == 200
            assert posted.headers["access-control-allow-origin"] == "https://claude.ai"
            # Without this the browser hides the session id from the transport.
            assert "mcp-session-id" in posted.headers["access-control-expose-headers"]


async def test_other_origins_get_no_cors_grant(db):
    app = mcp_server.create_app(TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            posted = await client.post(
                f"/mcp/{TOKEN}",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Origin": "https://evil.example",
                },
            )
            assert "access-control-allow-origin" not in posted.headers


async def test_league_rosters_cover_every_team_in_the_league_compactly(db):
    async with db() as session:
        session.add(
            Team(
                id="espn:l-1-t-2",
                league_id="espn:1",
                platform="espn",
                platform_id="l-1-t-2",
                name="Rival",
                manager_name="them",
                rank_current=2,
                rank_total=10,
                is_user_team=False,
            )
        )
        session.add(
            RosterSlot(
                team_id="espn:l-1-t-2",
                week=3,
                slot="WR1",
                player_id="espn:p-1",
                proj_points=12.5,
                actual_points=0.0,
                is_live=False,
                game_state="pre",
                status_text="",
            )
        )
        await session.commit()

    data = await call("get_league_rosters", team_id=TEAM)
    assert data["week"] == 3
    by_id = {t["team_id"]: t for t in data["teams"]}
    assert set(by_id) == {TEAM, "espn:l-1-t-2"}
    assert by_id[TEAM]["is_user_team"] is True and by_id[TEAM]["starters"] == []
    rival = by_id["espn:l-1-t-2"]
    assert rival["manager"] == "them"
    assert rival["starters"] == [
        {
            "slot": "WR1",
            "player_id": "espn:p-1",
            "name": "Hurt Guy",
            "pos": "WR",
            "nfl": "SF",
            "injury": "IR",
            "proj": 12.5,
            "pts": 0.0,
        }
    ]
