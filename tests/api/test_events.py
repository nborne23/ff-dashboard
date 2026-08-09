"""`GET /api/events` (task 8.5) — driven directly at the generator level per the task
guidance ("testing the event-generator function directly is acceptable if
EventSourceResponse streaming is flaky under test"), every call capped with
`asyncio.wait_for` so a bug can never hang the suite."""

import asyncio
import json

import pytest

from backend.gridiron.api.events import event_stream
from backend.gridiron.schemas.events import DataChangedEvent, LiveStateChangedEvent
from backend.gridiron.services import events, live_state

TIMEOUT = 1.0


class FakeRequest:
    """Minimal stand-in for `fastapi.Request` — only `is_disconnected()` is used by
    `event_stream`."""

    def __init__(self) -> None:
        self._disconnected = False

    def disconnect(self) -> None:
        self._disconnected = True

    async def is_disconnected(self) -> bool:
        return self._disconnected


@pytest.fixture(autouse=True)
def _reset_module_state():
    events.reset()
    live_state.reset_state()
    yield
    events.reset()
    live_state.reset_state()


@pytest.mark.asyncio
async def test_connect_immediately_replays_current_live_state() -> None:
    live_state.set_current_live_state("live")
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=TIMEOUT)

    first = await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)

    assert first["event"] == "live_state.changed"
    payload = json.loads(first["data"])
    assert payload["live_state"] == "live"
    assert LiveStateChangedEvent.model_validate(payload).live_state == "live"

    await gen.aclose()


@pytest.mark.asyncio
async def test_replay_reflects_off_day_default() -> None:
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=TIMEOUT)

    first = await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)

    assert json.loads(first["data"])["live_state"] == "off_day"
    await gen.aclose()


@pytest.mark.asyncio
async def test_published_event_is_streamed_to_the_connection() -> None:
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=TIMEOUT)
    await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)  # drain the replay

    events.publish(DataChangedEvent(scopes=["teams"], as_of="2025-12-07T18:00:00"))  # type: ignore[arg-type]

    delivered = await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)
    assert delivered["event"] == "data.changed"
    assert json.loads(delivered["data"])["scopes"] == ["teams"]

    await gen.aclose()


@pytest.mark.asyncio
async def test_heartbeat_fires_when_no_event_arrives_within_the_window() -> None:
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=0.05)
    await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)  # drain the replay

    heartbeat = await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)

    assert heartbeat["event"] == "heartbeat"
    await gen.aclose()


@pytest.mark.asyncio
async def test_subscribes_on_connect_and_unsubscribes_on_generator_close() -> None:
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=TIMEOUT)
    await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)

    assert events.subscriber_count() == 1

    await gen.aclose()

    assert events.subscriber_count() == 0


@pytest.mark.asyncio
async def test_stops_when_the_request_disconnects() -> None:
    request = FakeRequest()
    gen = event_stream(request, heartbeat_seconds=0.05)
    await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)  # drain the replay

    request.disconnect()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=TIMEOUT)

    assert events.subscriber_count() == 0
