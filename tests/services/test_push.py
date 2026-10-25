"""`services/push.py` — VAPID key lifecycle, subscription rules, and fan-out with the
network call (`pywebpush.webpush`) replaced (add-push-notifications). Keys are generated
per test; none is ever written to a tracked file."""

import base64
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import AppSetting, Base, Player, PlayerHighlight, PushSubscription
from backend.gridiron.services import push

APPLE = "https://web.push.apple.com/QGxyz"
GOOGLE = "https://fcm.googleapis.com/fcm/send/abc"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    fake = SimpleNamespace(
        gridiron_secret_key="test-secret", gridiron_base_url="https://imac.ts.net"
    )
    monkeypatch.setattr(push, "get_settings", lambda: fake)
    return fake


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "push.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


@pytest.fixture
def sent(monkeypatch):
    """Records every webpush call; `sent.status[endpoint]` picks the answer."""
    calls: list[dict] = []
    status: dict[str, int | Exception] = {}

    def fake_webpush(**kwargs):
        calls.append(kwargs)
        answer = status.get(kwargs["subscription_info"]["endpoint"], 201)
        if isinstance(answer, Exception):
            raise answer
        if answer >= 300:
            raise WebPushException("push failed", response=FakeResponse(answer, "BadJwtToken"))
        return FakeResponse(answer)

    monkeypatch.setattr(push, "webpush", fake_webpush)
    return SimpleNamespace(calls=calls, status=status)


async def _subscribe(session_factory, *endpoints: str) -> None:
    async with session_factory() as session:
        for endpoint in endpoints:
            await push.save_subscription(session, endpoint, "p256dh-key", "auth-key")


class TestKeys:
    def test_public_key_is_an_uncompressed_p256_point(self) -> None:
        public = push.public_key_for(push.generate_private_key())
        raw = base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
        assert len(raw) == 65 and raw[0] == 0x04

    @pytest.mark.asyncio
    async def test_key_is_generated_once_and_kept(self, session_factory) -> None:
        async with session_factory() as session:
            first = await push.get_public_key(session)
        async with session_factory() as session:
            assert await push.get_public_key(session) == first
            stored = await session.get(AppSetting, push.VAPID_KEY_SETTING)
            assert stored is not None and len(stored.value) <= 255

    @pytest.mark.asyncio
    async def test_unreadable_key_is_replaced_and_subscriptions_dropped(
        self, session_factory, settings
    ) -> None:
        async with session_factory() as session:
            first = await push.get_public_key(session)
        await _subscribe(session_factory, APPLE)

        settings.gridiron_secret_key = "rotated"
        async with session_factory() as session:
            assert await push.get_public_key(session) != first
            assert list((await session.execute(select(PushSubscription))).scalars()) == []


class TestSubscriptions:
    @pytest.mark.parametrize(
        "endpoint",
        [APPLE, GOOGLE, "https://updates.push.services.mozilla.com/wpush/v2/x"],
    )
    def test_known_push_services_are_allowed(self, endpoint) -> None:
        assert push.is_allowed_endpoint(endpoint)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://web.push.apple.com/x",
            "https://evil.example.com/x",
            "https://push.apple.com.evil.example/x",
            "https://localhost:8000/api/admin",
        ],
    )
    def test_anything_else_is_refused(self, endpoint) -> None:
        assert not push.is_allowed_endpoint(endpoint)

    @pytest.mark.asyncio
    async def test_save_is_an_upsert_by_endpoint(self, session_factory) -> None:
        await _subscribe(session_factory, APPLE)
        async with session_factory() as session:
            await push.save_subscription(session, APPLE, "new-p256dh", "new-auth")
            rows = list((await session.execute(select(PushSubscription))).scalars())
        assert [(r.p256dh, r.auth) for r in rows] == [("new-p256dh", "new-auth")]

    @pytest.mark.asyncio
    async def test_save_rejects_an_unknown_host(self, session_factory) -> None:
        async with session_factory() as session:
            with pytest.raises(push.InvalidSubscriptionError):
                await push.save_subscription(session, "https://evil.example.com/x", "k", "a")


MESSAGE = push.Message(title="Touchdown! A", body="b", url="/?highlight=1", tag="highlight-1")


class TestDeliver:
    @pytest.mark.asyncio
    async def test_fans_out_with_fresh_claims_ttl_and_urgency(self, session_factory, sent) -> None:
        await _subscribe(session_factory, APPLE, GOOGLE)

        async with session_factory() as session:
            assert await push.deliver(session, MESSAGE) == 2

        assert len(sent.calls) == 2
        # pywebpush writes `aud` into the dict it's handed; each send must get its own.
        assert sent.calls[0]["vapid_claims"] is not sent.calls[1]["vapid_claims"]
        assert all(c["vapid_claims"]["sub"] == "https://imac.ts.net" for c in sent.calls)
        assert all(c["ttl"] == push.TTL_SECONDS for c in sent.calls)
        assert all(c["headers"]["Urgency"] == "high" for c in sent.calls)
        assert json.loads(sent.calls[0]["data"]) == {
            "title": "Touchdown! A",
            "body": "b",
            "url": "/?highlight=1",
            "tag": "highlight-1",
        }
        async with session_factory() as session:
            rows = list((await session.execute(select(PushSubscription))).scalars())
        assert all(r.last_success_at is not None for r in rows)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("gone", [404, 410])
    async def test_forgotten_subscription_is_deleted(self, session_factory, sent, gone) -> None:
        await _subscribe(session_factory, APPLE, GOOGLE)
        sent.status[APPLE] = gone

        async with session_factory() as session:
            assert await push.deliver(session, MESSAGE) == 1
            rows = list((await session.execute(select(PushSubscription))).scalars())
        assert [r.endpoint for r in rows] == [GOOGLE]

    @pytest.mark.asyncio
    async def test_rejection_keeps_the_subscription(self, session_factory, sent) -> None:
        await _subscribe(session_factory, APPLE)
        sent.status[APPLE] = 403

        async with session_factory() as session:
            assert await push.deliver(session, MESSAGE) == 0
            assert len(list((await session.execute(select(PushSubscription))).scalars())) == 1

    @pytest.mark.asyncio
    async def test_network_error_is_swallowed(self, session_factory, sent) -> None:
        await _subscribe(session_factory, APPLE, GOOGLE)
        sent.status[APPLE] = ConnectionError("offline")

        async with session_factory() as session:
            assert await push.deliver(session, MESSAGE) == 1

    @pytest.mark.asyncio
    async def test_no_subscriptions_sends_nothing(self, session_factory, sent) -> None:
        async with session_factory() as session:
            assert await push.deliver(session, MESSAGE) == 0
        assert sent.calls == []


def _highlight(id_: int, kind: str = "touchdown", stat_key: str = "rec_td") -> PlayerHighlight:
    return PlayerHighlight(
        id=id_,
        sleeper_id="100",
        player_id="yahoo:p1",
        season=2026,
        week=8,
        kind=kind,
        stat_key=stat_key,
        ordinal=id_,
        yards=34,
        stat_line="6 rec · 112 yds · 2 TD",
        created_at=datetime(2026, 10, 25, 18, 0),
    )


class TestNotifyHighlights:
    def test_message_reads_like_the_in_app_card(self) -> None:
        message = push.highlight_message(_highlight(7), "Ja'Marr Chase")
        assert message.title == "Touchdown! Ja'Marr Chase"
        assert message.body == "34-yd receiving TD · 6 rec · 112 yds · 2 TD"
        assert message.url == "/?highlight=7"
        assert message.tag == "highlight-7"

    def test_describe_play_without_yards(self) -> None:
        assert push.describe_play("rush_40p", None) == "40+ yd run"
        assert push.describe_play("rec_td", None) == "Receiving TD"

    @pytest.mark.asyncio
    async def test_caps_the_burst_and_folds_the_rest(self, session_factory, sent) -> None:
        async with session_factory() as session:
            session.add(
                Player(
                    id="yahoo:p1",
                    platform="yahoo",
                    platform_id="p1",
                    name="Ja'Marr Chase",
                    position="WR",
                    nfl_team="CIN",
                    nfl_opponent=None,
                    nfl_game_id=None,
                    bye_week=None,
                    injury_status=None,
                )
            )
            await session.commit()
        await _subscribe(session_factory, APPLE)

        async with session_factory() as session:
            delivered = await push.notify_highlights(session, [_highlight(i) for i in range(1, 6)])

        assert delivered == push.MAX_PER_RUN
        bodies = [json.loads(c["data"])["body"] for c in sent.calls]
        assert bodies[-1].endswith("(+2 more)")
        assert not bodies[0].endswith("more)")

    @pytest.mark.asyncio
    async def test_never_raises(self, session_factory, monkeypatch) -> None:
        async def broken(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(push, "deliver", broken)
        async with session_factory() as session:
            assert await push.notify_highlights(session, [_highlight(1)]) == 0
