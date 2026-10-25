"""`GET /api/highlights` — the user's starters' touchdowns and big plays (add-play-highlights).

Reads only `player_highlights`, which `services/highlights.py` writes from the
`refresh_player_stats` job. The client keeps a cursor: `?after=<id>` returns what came
since, and `latest_id` is where to move it. Without `after` nothing is returned but the
cursor — a first open shouldn't replay the afternoon.

Only highlights from the last `REPLAY_WINDOW` come back, however old the cursor: a phone
woken at halftime gets the touchdown from five minutes ago, not the one from noon.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.models import Player, PlayerHighlight
from backend.gridiron.schemas import Envelope
from backend.gridiron.schemas.highlights import HighlightsData, PlayerHighlightOut
from backend.gridiron.services import fantasy_service

router = APIRouter(prefix="/api/highlights", tags=["highlights"])

REPLAY_WINDOW = timedelta(minutes=30)
MAX_RESULTS = 10


@router.get("", response_model=Envelope[HighlightsData])
async def get_highlights(
    response: Response,
    after: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_session),
) -> Envelope[HighlightsData]:
    latest_id = (await session.execute(select(func.max(PlayerHighlight.id)))).scalar_one()
    highlights: list[PlayerHighlightOut] = []
    if after is not None:
        since = datetime.now(UTC).replace(tzinfo=None) - REPLAY_WINDOW
        rows = (
            await session.execute(
                select(PlayerHighlight, Player)
                .join(Player, Player.id == PlayerHighlight.player_id)
                .where(PlayerHighlight.id > after, PlayerHighlight.created_at >= since)
                .order_by(PlayerHighlight.id)
                .limit(MAX_RESULTS)
            )
        ).all()
        highlights = [
            PlayerHighlightOut(
                id=h.id,
                kind=h.kind,
                stat_key=h.stat_key,
                yards=h.yards,
                stat_line=h.stat_line,
                player_id=p.id,
                player_name=p.name,
                position=p.position,
                nfl_team=p.nfl_team,
                headshot_url=fantasy_service._headshot_url(p.platform, p.platform_id),
                created_at=h.created_at,
            )
            for h, p in rows
        ]
    meta = await fantasy_service.build_meta(session, next_refresh_at=scheduler.next_run_time())
    # The cursor makes every response different; the SSE signal is what says "ask again".
    response.headers["Cache-Control"] = "no-store"
    return Envelope(data=HighlightsData(highlights=highlights, latest_id=latest_id), meta=meta)
