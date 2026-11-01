"""`/api/teams/{team_id}/league/matchups*` — every pairing in a team's league, for the
All Matchups screen and its read-only head-to-head.

Its own router (beside `api/teams.py`, same prefix and envelope) so the feature lands as
new files. Like every `/api/teams*` endpoint it serves only persisted rows (design.md D7).
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.api.teams import CACHE_CONTROL, _envelope, _not_found, _resolve_week
from backend.gridiron.db import get_session
from backend.gridiron.schemas import Envelope
from backend.gridiron.services import league_matchups
from backend.gridiron.services.league_matchups import LeagueMatchupDetail, LeagueMatchupsData

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_id}/league/matchups", response_model=Envelope[LeagueMatchupsData])
async def get_league_matchups(
    team_id: str,
    response: Response,
    week: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> Envelope[LeagueMatchupsData]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    week = await _resolve_week(session, week)
    data = await league_matchups.get_league_matchups(session, team_id, week)
    if data is None:
        raise _not_found("team_not_found", f"unknown team id: {team_id}")
    return await _envelope(session, data)


@router.get("/{team_id}/league/matchups/{matchup_id}", response_model=Envelope[LeagueMatchupDetail])
async def get_league_matchup(
    team_id: str,
    matchup_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Envelope[LeagueMatchupDetail]:
    response.headers["Cache-Control"] = CACHE_CONTROL
    detail = await league_matchups.get_league_matchup_detail(session, team_id, matchup_id)
    if detail is None:
        raise _not_found("matchup_not_found", f"no matchup {matchup_id} in team {team_id}'s league")
    return await _envelope(session, detail)
