"""The live-refresh polling tier: an `app_settings`-backed enum shared by the Settings
API (`api/settings.py`, task 7.4) and the adaptive scheduler (`scheduler.py`, task 8.3).

Pulled out of `api/settings.py` so the scheduler (which must not import from the `api`
layer) and `api/settings.py` share one definition instead of two copies drifting apart.
"""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import AppSetting

LiveTier = Literal["10s", "30s", "1m"]
LIVE_TIER_KEY = "live_tier"
DEFAULT_LIVE_TIER: LiveTier = "30s"

_SECONDS: dict[LiveTier, int] = {"10s": 10, "30s": 30, "1m": 60}


async def get_live_tier(session: AsyncSession) -> LiveTier:
    """The persisted tier, or `DEFAULT_LIVE_TIER` when never set."""
    row = await session.get(AppSetting, LIVE_TIER_KEY)
    return row.value if row is not None else DEFAULT_LIVE_TIER  # type: ignore[return-value]


def tier_seconds(tier: LiveTier) -> int:
    return _SECONDS[tier]
