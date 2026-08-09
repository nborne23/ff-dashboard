"""Shared literals and the response envelope, per design.md D12.

`Envelope[T]` is the wrapper every read endpoint returns:
`{ data: T, meta: { live_state, as_of, next_refresh_at, platforms } }`.
"""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

Platform = Literal["yahoo", "espn"]
LiveState = Literal["live", "game_day", "off_day"]

# The internal roster/matchup slot vocabulary (design.md D12).
Slot = Literal["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "K", "DST", "BN", "IR"]


class PlatformStatus(BaseModel):
    """`meta.platforms[platform]` — `{ ok: boolean; error?: string }`."""

    ok: bool
    error: str | None = None


class Meta(BaseModel):
    live_state: LiveState
    as_of: datetime
    next_refresh_at: datetime
    platforms: dict[Platform, PlatformStatus]


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta
