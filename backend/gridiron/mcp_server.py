"""Read-only MCP server over the persisted fantasy read model.

Lets a claude.ai custom connector (web, desktop, and the mobile app, which reuses web
connectors) ask about rosters, matchups, standings, waivers and lineup advice. Every tool
reads from the same normalized tables the dashboard does (design.md D7 — reads never fetch
upstream) by calling the service layer directly; there are no writes, no refresh triggers
and no draft mutations.

Served by its own process (`backend/mcp_main.py`, port 8001), NOT mounted in the main
FastAPI app: that app has unauthenticated `/api/admin` and `/api/connections` routes and is
meant to stay tailnet-only, while this one has to be reachable from Anthropic's cloud.

Claude's custom connectors accept only OAuth or no auth, never a static header, so the
endpoint's secret is the URL path itself: `/mcp/<GRIDIRON_MCP_TOKEN>`.
"""

import secrets
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.gridiron import scheduler
from backend.gridiron.db import async_session_factory
from backend.gridiron.models import Player, PlayerInjury, Team
from backend.gridiron.schemas import ProjectionSource
from backend.gridiron.services import fantasy_service, lineup

MIN_TOKEN_LENGTH = 24

# Display-only fields that cost context and mean nothing to a language model.
_NOISE_KEYS = frozenset(
    {
        "headshot_url",
        "logo_url",
        "logo_source_url",
        "logo_type",
        "accent_color",
        "nfl_game_id",
        "spark_last_6",
    }
)

INSTRUCTIONS = (
    "Read-only access to the user's fantasy football leagues (Yahoo + ESPN). "
    "Start with list_teams: it returns the user's own teams, and every other tool takes one "
    "of those team ids (e.g. 'espn:l-1-t-1'). Omit `week` to use the current week. Data is "
    "the dashboard's last refresh, so check `as_of` before calling anything 'live'."
)


def _slim(value: Any) -> Any:
    """Drop display-only keys at any depth."""
    if isinstance(value, dict):
        return {k: _slim(v) for k, v in value.items() if k not in _NOISE_KEYS}
    if isinstance(value, list):
        return [_slim(v) for v in value]
    return value


def _dump(model: Any) -> Any:
    return _slim(model.model_dump(mode="json"))


class NotFoundError(ToolError):
    """Surfaced to the model as a tool error rather than an empty result."""


def _require(value: Any, what: str, hint: str = " Call list_teams for valid team ids.") -> Any:
    if value is None:
        raise NotFoundError(f"{what}.{hint}")
    return value


async def _meta(session) -> dict[str, Any]:
    # This process runs no scheduler and shares none of the main app's in-memory cooldown
    # state, so `next_refresh_at` is always null and `platforms` can miss a cooldown. `as_of`
    # comes from the database and is accurate.
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    return meta.model_dump(mode="json")


def _roster_line(slot: Any) -> dict[str, Any]:
    p = slot.player
    return {
        "slot": slot.slot,
        "player_id": p.id,
        "name": p.name,
        "pos": p.position,
        "nfl": p.nfl_team,
        "injury": p.injury_status,
        "proj": slot.proj_points,
        "pts": slot.actual_points,
    }


def build_server() -> MCPServer:
    server = MCPServer("GridIron", instructions=INSTRUCTIONS)

    @server.tool()
    async def list_teams(week: int | None = None) -> dict[str, Any]:
        """The user's fantasy teams across all enabled leagues: record, standing, points,
        and the current score vs. opponent. Start here to get team ids."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            teams = await fantasy_service.list_teams(session, wk)
            return {"week": wk, "teams": [_dump(t) for t in teams], "meta": await _meta(session)}

    @server.tool()
    async def game_day(week: int | None = None) -> dict[str, Any]:
        """Every user team's head-to-head this week in one call: scores, projections and
        players remaining. The best answer to "how am I doing right now?". Omits per-player
        rows; use get_matchup for one team's slot-by-slot detail."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            data = await fantasy_service.game_day(session, wk)
            matchups = []
            for m in data.matchups:
                row = _dump(m)
                row.pop("slots", None)  # per-player rows live in get_matchup
                matchups.append(row)
            return {"week": wk, "matchups": matchups, "meta": await _meta(session)}

    @server.tool()
    async def get_team(team_id: str, week: int | None = None) -> dict[str, Any]:
        """One team's roster for the week: starters, bench, projections and injury
        designations, plus its week-by-week record."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            detail = _require(
                await fantasy_service.get_team(session, team_id, wk), f"No team {team_id!r}"
            )
            return {"week": wk, **_dump(detail), "meta": await _meta(session)}

    @server.tool()
    async def get_matchup(team_id: str, week: int | None = None) -> dict[str, Any]:
        """Head-to-head detail for one team's week: both lineups slot by slot with points,
        projections and game state, and how many players each side has left."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            h2h = _require(
                await fantasy_service.get_h2h(session, team_id, wk),
                f"No matchup for team {team_id!r} in week {wk}",
                hint=" The league may have no matchup scheduled yet.",
            )
            return {"week": wk, **_dump(h2h), "meta": await _meta(session)}

    @server.tool()
    async def get_season(team_id: str) -> dict[str, Any]:
        """A team's season so far: every week's score and result, plus highlights (season
        high, win streak, most-started player)."""
        async with async_session_factory() as session:
            season = _require(
                await fantasy_service.get_season(session, team_id), f"No team {team_id!r}"
            )
            return {**_dump(season), "meta": await _meta(session)}

    @server.tool()
    async def get_league_standings(team_id: str) -> dict[str, Any]:
        """Full standings for the league this team plays in."""
        async with async_session_factory() as session:
            standings = _require(
                await fantasy_service.get_league_standings(session, team_id),
                f"No team {team_id!r}",
            )
            return {**_dump(standings), "meta": await _meta(session)}

    @server.tool()
    async def get_waivers(
        team_id: str, position: str | None = None, limit: int = 15, week: int | None = None
    ) -> dict[str, Any]:
        """Claimable free agents in the team's league, ranked, each measured against the
        starter it would replace. `position` is QB/RB/WR/TE/K/DST."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            waivers = _require(
                await fantasy_service.get_waivers(
                    session, team_id, wk, position, max(1, min(limit, 50))
                ),
                f"No team {team_id!r}",
            )
            return {"week": wk, **_dump(waivers), "meta": await _meta(session)}

    @server.tool()
    async def get_lineup_advice(
        team_id: str, week: int | None = None, source: ProjectionSource = "rotowire"
    ) -> dict[str, Any]:
        """The optimal legal lineup for the week and the start/sit moves that reach it.
        `source` picks the projections: 'rotowire' (independent, default) or 'platform'
        (what the league host's own numbers would recommend)."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            advice = _require(
                await lineup.get_lineup_advice(session, team_id, wk, source),
                f"No team {team_id!r}",
            )
            return {"week": wk, **_dump(advice), "meta": await _meta(session)}

    @server.tool()
    async def get_league_rosters(team_id: str, week: int | None = None) -> dict[str, Any]:
        """Every team's roster in the league this team plays in, compactly: one line per
        player (slot, name, position, NFL team, injury, projection, points). Use it to
        scout opponents, trade partners and who holds a player. A team with no rows has no
        roster synced for that week (e.g. the season hasn't started)."""
        async with async_session_factory() as session:
            wk = week if week is not None else await fantasy_service.current_week(session)
            row = _require(await session.get(Team, team_id), f"No team {team_id!r}")
            league_teams = (
                (
                    await session.execute(
                        select(Team).where(Team.league_id == row.league_id).order_by(Team.id)
                    )
                )
                .scalars()
                .all()
            )
            teams = []
            for t in league_teams:
                detail = await fantasy_service.get_team(session, t.id, wk)
                if detail is None:
                    continue
                teams.append(
                    {
                        "team_id": t.id,
                        "name": t.name,
                        "manager": t.manager_name,
                        "is_user_team": t.is_user_team,
                        "record": f"{t.record_w}-{t.record_l}-{t.record_t}",
                        "starters": [_roster_line(s) for s in detail.starters],
                        "bench": [_roster_line(s) for s in detail.bench],
                    }
                )
            return {
                "week": wk,
                "league": row.league_id,
                "teams": teams,
                "meta": await _meta(session),
            }

    @server.tool()
    async def get_player_injury(player_id: str) -> dict[str, Any]:
        """Injury report for one player (ids come from rosters and waivers). `report` is
        null when no detailed report is on file, which usually means healthy."""
        async with async_session_factory() as session:
            player = _require(await session.get(Player, player_id), f"No player {player_id!r}")
            row = (
                await session.execute(
                    select(PlayerInjury).where(PlayerInjury.player_id == player_id)
                )
            ).scalar_one_or_none()
            report = None
            if row is not None:
                report = {
                    "status": row.status,
                    "injury_type": row.injury_type,
                    "location": row.location,
                    "detail": row.detail,
                    "return_date": row.return_date,
                    "short_comment": row.short_comment,
                    "long_comment": row.long_comment,
                    "reported_at": row.reported_at.isoformat() if row.reported_at else None,
                }
            return {
                "player_id": player_id,
                "name": player.name,
                "injury_status": player.injury_status,
                "report": report,
            }

    return server


def create_app(token: str) -> Starlette:
    """ASGI app serving the MCP endpoint at `/mcp/<token>` and nothing else (every other
    path 404s, so the secret is the only way in)."""
    if len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(
            f"GRIDIRON_MCP_TOKEN must be set to at least {MIN_TOKEN_LENGTH} characters. "
            'Generate one: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    server = build_server()
    mcp_app = server.streamable_http_app(
        streamable_http_path=f"/mcp/{token}",
        json_response=True,
        stateless_http=True,
        # The Host header is the public Funnel hostname; the secret path is the gate, so
        # the DNS-rebinding allowlist (which only knows localhost) would reject every call.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def health(_request) -> JSONResponse:
        return JSONResponse({"ok": True})

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = Starlette(
        routes=[Route("/healthz", health), *mcp_app.routes],
        lifespan=lifespan,
    )
    return app


def new_token() -> str:
    return secrets.token_urlsafe(32)
