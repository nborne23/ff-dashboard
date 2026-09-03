"""`/api/teams*` — the read API for the frontend (fantasy-data-model spec, task 3.10).

Every endpoint returns the `Envelope` (design.md D12) and serves ONLY from the persisted
normalized tables (design.md D7 — reads never fetch upstream). Responses carry
`Cache-Control: private, max-age=15, stale-while-revalidate=30` so bursts of
invalidation-driven refetches coalesce in the browser cache.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.schemas import Envelope, LineupAdvice, ProjectionSource, WaiversData
from backend.gridiron.services import fantasy_service, lineup
from backend.gridiron.services.fantasy_service import (
    H2HData,
    SeasonData,
    TeamDetailData,
    TeamsData,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])

CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


async def _envelope(session: AsyncSession, data) -> Envelope:
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    return Envelope(data=data, meta=meta)


async def _resolve_week(session: AsyncSession, week: int | None) -> int:
    return week if week is not None else await fantasy_service.current_week(session)


@router.get("", response_model=Envelope[TeamsData])
async def list_teams(
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[TeamsData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    teams = await fantasy_service.list_teams(session, week)
    return await _envelope(session, TeamsData(teams=teams))


# Registered before `/{team_id}` (task 10.6) — FastAPI/Starlette match routes in
# registration order, so "day-rings" would otherwise be swallowed as a team id.
@router.get("/day-rings", response_model=Envelope[fantasy_service.DayRingsData])
async def get_day_rings(
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[fantasy_service.DayRingsData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    data = await fantasy_service.day_rings(session, week)
    return await _envelope(session, data)


# Registered before `/{team_id}` for the same reason `/day-rings` is: FastAPI/Starlette
# match in registration order, so "game-day" would otherwise be swallowed as a team id
# and 404 out of `get_team` (fantasy-data-model spec, "Route registration order").
@router.get("/game-day", response_model=Envelope[fantasy_service.GameDayData])
async def get_game_day(
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[fantasy_service.GameDayData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    data = await fantasy_service.game_day(session, week)
    return await _envelope(session, data)


@router.get("/{team_id}", response_model=Envelope[TeamDetailData])
async def get_team(
    team_id: str,
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[TeamDetailData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    detail = await fantasy_service.get_team(session, team_id, week)
    if detail is None:
        raise _not_found("team_not_found", f"unknown team id: {team_id}")
    return await _envelope(session, detail)


@router.get("/{team_id}/h2h", response_model=Envelope[H2HData])
async def get_h2h(
    team_id: str,
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[H2HData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    h2h = await fantasy_service.get_h2h(session, team_id, week)
    if h2h is None:
        raise _not_found("matchup_not_found", f"no matchup for team {team_id} in week {week}")
    return await _envelope(session, h2h)


@router.get("/{team_id}/season", response_model=Envelope[SeasonData])
async def get_season(
    team_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Envelope[SeasonData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    season = await fantasy_service.get_season(session, team_id)
    if season is None:
        raise _not_found("team_not_found", f"unknown team id: {team_id}")
    return await _envelope(session, season)


@router.get("/{team_id}/waivers", response_model=Envelope[WaiversData])
async def get_waivers(
    team_id: str,
    response: Response,
    week: int | None = None,
    position: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> Envelope[WaiversData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    waivers = await fantasy_service.get_waivers(session, team_id, week, position, limit)
    if waivers is None:
        raise _not_found("team_not_found", f"unknown team id: {team_id}")
    return await _envelope(session, waivers)


@router.get("/{team_id}/league", response_model=Envelope[fantasy_service.LeagueStandingsData])
async def get_league_standings(
    team_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Envelope[fantasy_service.LeagueStandingsData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    standings = await fantasy_service.get_league_standings(session, team_id)
    if standings is None:
        raise _not_found("team_not_found", f"unknown team id: {team_id}")
    return await _envelope(session, standings)


@router.get("/{team_id}/lineup", response_model=Envelope[LineupAdvice])
async def get_lineup(
    team_id: str,
    response: Response,
    week: int | None = None,
    source: ProjectionSource = "rotowire",
    session: AsyncSession = Depends(get_session),
) -> Envelope:
    """Optimal legal lineup for `week` and the moves that reach it.

    `source` defaults to `rotowire` — the independent projection is the reason this
    endpoint can say anything the platform's own app doesn't already. Pass `platform` to
    see what your league host's numbers would recommend instead.
    """
    resolved = await _resolve_week(session, week)
    data = await lineup.get_lineup_advice(session, team_id, resolved, source)
    if data is None:
        raise _not_found("team_not_found", f"no team {team_id!r}")
    response.headers["Cache-Control"] = CACHE_CONTROL
    return await _envelope(session, data)
