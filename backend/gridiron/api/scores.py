"""`GET /api/scores` and `GET /api/scores/games/{game_id}` — the NFL Scores screen (add-nfl-scores).

Reads only what `refresh_nfl_state`, `refresh_nfl_weeks` and `refresh_player_stats` left
behind (design.md D7); see `services/scores.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.schemas import Envelope
from backend.gridiron.schemas.scores import GameDetail, ScoresWeek
from backend.gridiron.services import fantasy_service, nfl_week_cache, scores

router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("", response_model=Envelope[ScoresWeek])
async def get_scores(
    week: int | None = Query(default=None, ge=1, le=nfl_week_cache.MAX_WEEK),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ScoresWeek]:
    data = await scores.week_scores(session, week)
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    return Envelope(data=data, meta=meta)


@router.get("/games/{game_id}", response_model=Envelope[GameDetail])
async def get_game(
    game_id: str,
    league_id: str | None = None,
    week: int | None = Query(default=None, ge=1, le=nfl_week_cache.MAX_WEEK),
    session: AsyncSession = Depends(get_session),
) -> Envelope[GameDetail]:
    data = await scores.game_detail(session, game_id, league_id, week)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no cached game {game_id!r}")
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    return Envelope(data=data, meta=meta)
