"""`/api/leagues` — list every discovered league (both platforms) and toggle whether a
league counts toward the app (task 7.3, Settings' "ESPN Leagues" card).

Plain list response, not the `Envelope` (design.md D12) — this is Settings config data,
not a Dashboard read that needs `live_state`/`as_of`/`platforms` freshness metadata.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import schemas
from backend.gridiron.db import get_session
from backend.gridiron.models import League

router = APIRouter(prefix="/api/leagues", tags=["leagues"])


class LeagueOut(BaseModel):
    id: str
    platform: schemas.Platform
    platform_id: str
    name: str
    season: int
    team_count: int
    scoring_type: schemas.ScoringType
    current_week: int
    is_enabled: bool


class LeagueUpdateRequest(BaseModel):
    is_enabled: bool


def _to_out(row: League) -> LeagueOut:
    return LeagueOut(
        id=row.id,
        platform=row.platform,
        platform_id=row.platform_id,
        name=row.name,
        season=row.season,
        team_count=row.team_count,
        scoring_type=row.scoring_type,
        current_week=row.current_week,
        is_enabled=row.is_enabled,
    )


@router.get("", response_model=list[LeagueOut])
async def list_leagues(session: AsyncSession = Depends(get_session)) -> list[LeagueOut]:
    rows = (
        (await session.execute(select(League).order_by(League.platform, League.name)))
        .scalars()
        .all()
    )
    return [_to_out(row) for row in rows]


@router.patch("/{league_id}", response_model=LeagueOut)
async def update_league(
    league_id: str,
    body: LeagueUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> LeagueOut:
    row = await session.get(League, league_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "league_not_found", "message": f"unknown league id: {league_id}"},
        )
    row.is_enabled = body.is_enabled
    await session.commit()
    await session.refresh(row)
    return _to_out(row)
