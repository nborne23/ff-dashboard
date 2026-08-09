"""`services/events.py` — the in-process SSE pub/sub bus (task 8.4)."""

import asyncio
from datetime import datetime, timedelta

import pytest

from backend.gridiron.schemas.events import HeartbeatEvent, LiveStateChangedEvent
from backend.gridiron.services import events

BASE_TIME = datetime(2025, 1, 1, 0, 0, 0)


@pytest.fixture(autouse=True)
def _reset_bus():
    events.reset()
    yield
    events.reset()


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_every_published_event() -> None:
    queues = [events.subscribe() for _ in range(3)]
    assert events.subscriber_count() == 3

    first = LiveStateChangedEvent(live_state="live")
    second = LiveStateChangedEvent(live_state="off_day")
    events.publish(first)
    events.publish(second)

    for queue in queues:
        assert queue.get_nowait() == first
        assert queue.get_nowait() == second


@pytest.mark.asyncio
async def test_unsubscribe_stops_further_delivery() -> None:
    queue = events.subscribe()
    events.unsubscribe(queue)
    assert events.subscriber_count() == 0

    events.publish(LiveStateChangedEvent(live_state="live"))
    assert queue.empty()


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_a_no_op() -> None:
    events.publish(LiveStateChangedEvent(live_state="live"))  # must not raise
    assert events.subscriber_count() == 0


@pytest.mark.asyncio
async def test_overflow_drops_the_oldest_event_not_the_newest() -> None:
    queue = events.subscribe()
    oldest = HeartbeatEvent(at=BASE_TIME)
    for i in range(events.MAX_QUEUE_SIZE):
        at = BASE_TIME if i == 0 else BASE_TIME + timedelta(seconds=i)
        events.publish(HeartbeatEvent(at=at))

    assert queue.full()
    # One more event should evict the oldest and admit the newest.
    newest = HeartbeatEvent(at=BASE_TIME + timedelta(minutes=5))
    events.publish(newest)

    assert queue.qsize() == events.MAX_QUEUE_SIZE
    drained = [queue.get_nowait() for _ in range(events.MAX_QUEUE_SIZE)]
    assert oldest not in drained  # the oldest got dropped to make room
    assert drained[-1] == newest  # the newest made it in


@pytest.mark.asyncio
async def test_reset_clears_subscriptions() -> None:
    events.subscribe()
    events.subscribe()
    assert events.subscriber_count() == 2

    events.reset()

    assert events.subscriber_count() == 0


def test_subscribe_returns_a_bounded_asyncio_queue() -> None:
    queue = events.subscribe()
    assert isinstance(queue, asyncio.Queue)
    assert queue.maxsize == events.MAX_QUEUE_SIZE
