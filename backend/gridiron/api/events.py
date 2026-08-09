"""`GET /api/events` — SSE push (task 8.5).

"SSE is the signal, REST is the data": every event either carries no payload
(heartbeat) or just enough for the frontend to know *what* to invalidate/refetch
(`data.changed`'s `scopes`, `live_state.changed`/`tier.change`'s new value) — never
entity payloads. On connect, the client immediately replays the current `live_state`
(so a fresh page load doesn't have to wait for the next `refresh_nfl_state` tick to know
whether anything's live) and then streams bus events as they arrive, interleaved with a
heartbeat whenever nothing else has fired in `HEARTBEAT_SECONDS`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.gridiron.schemas.events import HeartbeatEvent, LiveStateChangedEvent, SseEvent
from backend.gridiron.services import events, live_state

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["events"])

HEARTBEAT_SECONDS = 15


def _to_sse(event: SseEvent) -> dict:
    return {"event": event.type, "data": event.model_dump_json()}


async def event_stream(
    request: Request, heartbeat_seconds: float = HEARTBEAT_SECONDS
) -> AsyncIterator[dict]:
    """The actual generator driving the SSE response — a free function (not a closure)
    so tests can drive it directly with a fake `Request` and a short `heartbeat_seconds`
    instead of going through a real streaming HTTP connection."""
    queue = events.subscribe()
    try:
        yield _to_sse(LiveStateChangedEvent(live_state=live_state.get_current_live_state()))
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield _to_sse(HeartbeatEvent(at=datetime.now(UTC).replace(tzinfo=None)))
                continue
            yield _to_sse(event)
    finally:
        events.unsubscribe(queue)


@router.get("/api/events")
async def stream_events(request: Request) -> EventSourceResponse:
    return EventSourceResponse(event_stream(request))
