"""`/api/players/{player_id}/injury` — per-player health detail (add-player-health).

`/api/players/{player_id}/stats` — game log, season totals, and this week's stat line and
points breakdown (add-player-stats). Same rule: reads only.

Serves ONLY from `player_injuries` (design.md D7 — reads never fetch upstream); the
`refresh_injuries` scheduler job is the sole writer. A player with no stored report is a
`200` with `report: null`, not a `404`: "healthy" is the overwhelmingly common answer and
the panel renders it as content, not as an error.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.models import Player, PlayerInjury
from backend.gridiron.platforms import espn_injuries
from backend.gridiron.schemas import (
    Envelope,
    PlayerInjuryData,
    PlayerInjuryReport,
    PlayerStatsData,
)
from backend.gridiron.services import fantasy_service, player_stats

router = APIRouter(prefix="/api/players", tags=["players"])

# Shorter than the 15s the team reads use: an injury report is refreshed every 30 minutes
# and a stale one is misleading in a way a stale score isn't.
CACHE_CONTROL = "private, max-age=60, stale-while-revalidate=120"

# The team reads' window: this week's stat line moves with the live refresh.
STATS_CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=30"


def _to_report(row: PlayerInjury) -> PlayerInjuryReport:
    return PlayerInjuryReport(
        status=row.status,
        injury_type=row.injury_type,
        location=row.location,
        detail=row.detail,
        side=row.side,
        return_date=row.return_date,
        short_comment=row.short_comment,
        long_comment=row.long_comment,
        reported_at=row.reported_at,
        fetched_at=row.fetched_at,
    )


@router.get("/{player_id}/injury", response_model=Envelope[PlayerInjuryData])
async def get_player_injury(
    player_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlayerInjuryData]:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "player_not_found", "message": f"no player {player_id!r}"},
        )

    row = (
        await session.execute(select(PlayerInjury).where(PlayerInjury.player_id == player_id))
    ).scalar_one_or_none()

    data = PlayerInjuryData(
        player_id=player_id,
        injury_status=player.injury_status,
        report=_to_report(row) if row is not None else None,
        detail_supported=espn_injuries.detail_supported(player_id, player.espn_athlete_id),
    )
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    response.headers["Cache-Control"] = CACHE_CONTROL
    return Envelope(data=data, meta=meta)


@router.get("/{player_id}/stats", response_model=Envelope[PlayerStatsData])
async def get_player_stats(
    player_id: str,
    response: Response,
    team_id: str | None = Query(
        default=None,
        description="The viewing team: picks the league's points format and roster slot.",
    ),
    week: int | None = Query(default=None, ge=1, le=18),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlayerStatsData]:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "player_not_found", "message": f"no player {player_id!r}"},
        )
    data = await player_stats.build(session, player, team_id, week)
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    response.headers["Cache-Control"] = STATS_CACHE_CONTROL
    return Envelope(data=data, meta=meta)
