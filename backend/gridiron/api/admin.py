"""`/api/admin/*` — manual refresh trigger + refresh-run history (task 3.12).

No auth by design (design.md D8): the process is reachable only from tailnet devices or
localhost, so the manual trigger needs no secret. The trigger calls the job coroutine
directly through `scheduler.run_job`, so it works even when the scheduler is disabled
(the dev default).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.models import RefreshRun
from backend.gridiron.scheduler import UnknownJobError

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RefreshRunResult(BaseModel):
    id: int
    job_name: str
    run_at: datetime
    ok: bool
    error: str | None
    duration_ms: int


def _to_result(run: RefreshRun) -> RefreshRunResult:
    return RefreshRunResult(
        id=run.id,
        job_name=run.job_name,
        run_at=run.run_at,
        ok=run.ok,
        error=run.error,
        duration_ms=run.duration_ms,
    )


@router.post("/refresh", response_model=RefreshRunResult)
async def refresh_now(
    job: str = "sync_discovery",
    session: AsyncSession = Depends(get_session),
) -> RefreshRunResult:
    try:
        run = await scheduler.run_job(job, session)
    except UnknownJobError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "unknown_job", "message": str(exc)}
        ) from exc
    return _to_result(run)


@router.get("/refresh-runs", response_model=list[RefreshRunResult])
async def refresh_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[RefreshRunResult]:
    limit = max(1, min(limit, 200))
    rows = (
        (
            await session.execute(
                select(RefreshRun)
                .order_by(RefreshRun.run_at.desc(), RefreshRun.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_to_result(run) for run in rows]
