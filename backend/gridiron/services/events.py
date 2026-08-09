"""In-process asyncio pub/sub bus for SSE (task 8.4).

Each connected `/api/events` client (`api/events.py`) owns one bounded `asyncio.Queue`;
`publish` fans an event out to every subscriber. Deliberately synchronous (no I/O, no
`await` needed anywhere in here) so callers — job coroutines, API handlers — can call
`publish` without ceremony.

Queue-overflow policy: **drop-oldest**. A slow/stalled subscriber loses its oldest
buffered event rather than blocking `publish` (which would stall every *other*
subscriber and the caller — a scheduler job) or being disconnected outright. This is
safe specifically because SSE events here are non-authoritative signals ("something
changed, go refetch") rather than the data itself (see the module docstring in
`schemas/events.py` / the design principle "SSE is the signal, REST is the data") — losing
a stale `data.changed` in favor of a fresher one loses no information the frontend cares
about.

No globals leak between tests: `reset()` clears every subscription.
"""

import asyncio
import logging

from backend.gridiron.schemas.events import SseEvent

logger = logging.getLogger("uvicorn.error")

MAX_QUEUE_SIZE = 32

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> "asyncio.Queue[SseEvent]":
    """Register a new subscriber and return its queue. Callers must `unsubscribe` it
    (typically in a `finally`) when the client disconnects."""
    queue: "asyncio.Queue[SseEvent]" = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: "asyncio.Queue[SseEvent]") -> None:
    _subscribers.discard(queue)


def publish(event: SseEvent) -> None:
    """Fan `event` out to every current subscriber (drop-oldest on a full queue)."""
    for queue in list(_subscribers):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()  # drop the oldest buffered event to make room
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE subscriber queue still full after drop-oldest; dropping event")


def subscriber_count() -> int:
    """Number of active subscriptions (test/debug helper)."""
    return len(_subscribers)


def reset() -> None:
    """Clear every subscription (test isolation — mirrors `fantasy_service.reset_state`)."""
    _subscribers.clear()
