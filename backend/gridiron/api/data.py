"""`DELETE /api/cache` + `GET /api/export.json` — Settings' "Data Management" card
(task 7.7). Neither resource shares a natural prefix with an existing router, so this
module registers both absolute paths directly rather than using `APIRouter(prefix=...)`.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.db import get_session
from backend.gridiron.models import HttpCache, League, Matchup, Player, RosterSlot, SeasonWeek, Team

router = APIRouter(tags=["data"])


@router.delete("/api/cache", status_code=204)
async def clear_cache(session: AsyncSession = Depends(get_session)) -> None:
    """Delete every cached upstream response. Read endpoints still serve normalized rows
    (design.md D7 is unaffected) — this only forces the *next* refresh to hit Yahoo/ESPN
    instead of a cache hit."""
    await session.execute(delete(HttpCache))
    await session.commit()


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Dump every mapped column of an ORM row to a JSON-safe dict (datetimes -> ISO 8601)."""
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        result[column.name] = value
    return result


@router.get("/api/export.json")
async def export_data(session: AsyncSession = Depends(get_session)) -> Response:
    """A full JSON dump of the normalized tables, for the "Export data" button — a manual
    backup / take-your-data-with-you escape hatch, not an API other code should depend on."""
    payload: dict[str, Any] = {"exported_at": datetime.now(UTC).isoformat()}
    for key, model in (
        ("leagues", League),
        ("teams", Team),
        ("players", Player),
        ("roster_slots", RosterSlot),
        ("matchups", Matchup),
        ("season_weeks", SeasonWeek),
    ):
        rows = (await session.execute(select(model))).scalars().all()
        payload[key] = [_row_to_dict(row) for row in rows]

    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=gridiron-export.json"},
    )
