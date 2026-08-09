"""`SseEvent` — the discriminated union of events pushed over `/api/events` (design.md D12)."""

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from backend.gridiron.schemas.common import LiveState


class DataChangedEvent(BaseModel):
    type: Literal["data.changed"] = "data.changed"
    scopes: list[str]
    as_of: datetime


class LiveStateChangedEvent(BaseModel):
    type: Literal["live_state.changed"] = "live_state.changed"
    live_state: LiveState


class TierChangeEvent(BaseModel):
    type: Literal["tier.change"] = "tier.change"
    live_tier_seconds: int


class HeartbeatEvent(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    at: datetime


SseEvent = Annotated[
    Union[DataChangedEvent, LiveStateChangedEvent, TierChangeEvent, HeartbeatEvent],
    Field(discriminator="type"),
]
