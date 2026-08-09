"""`/api/settings` — small server-persisted app settings (task 7.4). Today this is just
the live-refresh polling tier the Settings screen's PreferencesCard controls; the
notification toggles next to it in the prototype are client-only (functionally inert),
so they don't need a backend row.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron import scheduler
from backend.gridiron.db import get_session
from backend.gridiron.models import AppSetting
from backend.gridiron.schemas.events import TierChangeEvent
from backend.gridiron.services import events, live_tier
from backend.gridiron.services.live_tier import DEFAULT_LIVE_TIER, LIVE_TIER_KEY, LiveTier

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    live_tier: LiveTier


class LiveTierRequest(BaseModel):
    live_tier: LiveTier


@router.get("", response_model=SettingsOut)
async def get_app_settings(session: AsyncSession = Depends(get_session)) -> SettingsOut:
    row = await session.get(AppSetting, LIVE_TIER_KEY)
    live_tier: LiveTier = row.value if row is not None else DEFAULT_LIVE_TIER  # type: ignore[assignment]
    return SettingsOut(live_tier=live_tier)


@router.post("/live-tier", response_model=SettingsOut)
async def set_live_tier(
    body: LiveTierRequest, session: AsyncSession = Depends(get_session)
) -> SettingsOut:
    row = await session.get(AppSetting, LIVE_TIER_KEY)
    if row is None:
        session.add(AppSetting(key=LIVE_TIER_KEY, value=body.live_tier))
    else:
        row.value = body.live_tier
    await session.commit()

    # Reschedule the running refresh_fantasy job immediately (only actually changes its
    # cadence while live_state == "live" — see scheduler.reschedule_refresh_fantasy; a
    # no-op when the scheduler isn't running) and let already-open SSE clients know.
    await scheduler.reschedule_refresh_fantasy(session)
    events.publish(TierChangeEvent(live_tier_seconds=live_tier.tier_seconds(body.live_tier)))

    return SettingsOut(live_tier=body.live_tier)
