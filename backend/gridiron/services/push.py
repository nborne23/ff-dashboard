"""Web Push: the VAPID key, subscriptions, and sending highlights (add-push-notifications).

Delivery path: iMac -> the browser's push service (Apple's for a Home Screen app on
iOS 16.4+) -> the phone's service worker (`frontend/public/sw.js`), which shows the
notification. The iMac only needs outbound internet, so this works off the tailnet.

The VAPID key is generated on first use and kept, Fernet-encrypted like every other
credential, in `app_settings`. It has to stay put: every subscription is bound to the
public key it was created with, so a new key orphans them all. If it can't be decrypted
(the secret key changed) it is regenerated AND every subscription is dropped, and each
device resubscribes on its next open — `api/push.py` serves the new public key, and the
frontend notices the mismatch.

pywebpush is synchronous (`requests`), so each send runs in a worker thread.
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.config import get_settings
from backend.gridiron.errors import CredentialDecryptError
from backend.gridiron.models import AppSetting, Player, PlayerHighlight, PushSubscription
from backend.gridiron.services import credentials

logger = logging.getLogger("uvicorn.error")

VAPID_KEY_SETTING = "push_vapid_private_key"

# How long a push service holds a message for a phone that's offline. pywebpush's default
# is 0 — "deliver now or drop" — which loses the touchdown to a moment in a tunnel. Past
# 15 minutes it's old news, and the in-app feed covers the rest anyway.
TTL_SECONDS = 15 * 60

# VAPID JWT lifetime. Apple rejects tokens that live too long; an hour is the common floor.
TOKEN_SECONDS = 60 * 60

SEND_TIMEOUT_SECONDS = 10

# Same cap as the in-app queue (`frontend/src/stores/highlights.ts` MAX_QUEUED): a burst
# past it folds into "+N more" on the last one instead of buzzing the phone five times.
MAX_PER_RUN = 3

# The server POSTs to whatever endpoint a client registers, so only real push services
# are accepted: Apple (Safari / Home Screen apps), Google (Chrome), Mozilla, Microsoft.
ALLOWED_PUSH_HOSTS = (
    "push.apple.com",
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
)


class InvalidSubscriptionError(ValueError):
    """The endpoint isn't an https URL on a known push service."""


def is_allowed_endpoint(endpoint: str) -> bool:
    url = urlparse(endpoint)
    host = url.hostname or ""
    return url.scheme == "https" and any(
        host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_PUSH_HOSTS
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_private_key() -> str:
    """A fresh P-256 private key as base64url of its 32 raw bytes (fits `app_settings`)."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def public_key_for(private_raw: str) -> str:
    """The `applicationServerKey` browsers subscribe with: base64url of the 65-byte
    uncompressed public point."""
    vapid = Vapid.from_raw(private_raw.encode("ascii"))
    return _b64url(vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


async def get_private_key(session: AsyncSession) -> str:
    secret = get_settings().gridiron_secret_key
    row = await session.get(AppSetting, VAPID_KEY_SETTING)
    if row is not None:
        try:
            return credentials.decrypt(secret, row.value)
        except CredentialDecryptError:
            logger.warning("push: VAPID key unreadable (secret changed?); regenerating")
            await session.execute(delete(PushSubscription))

    private_raw = generate_private_key()
    encrypted = credentials.encrypt(secret, private_raw)
    if row is None:
        session.add(AppSetting(key=VAPID_KEY_SETTING, value=encrypted))
    else:
        row.value = encrypted
    await session.commit()
    return private_raw


async def get_public_key(session: AsyncSession) -> str:
    return public_key_for(await get_private_key(session))


async def save_subscription(session: AsyncSession, endpoint: str, p256dh: str, auth: str) -> None:
    if not is_allowed_endpoint(endpoint):
        raise InvalidSubscriptionError(endpoint)
    stmt = insert(PushSubscription).values(endpoint=endpoint, p256dh=p256dh, auth=auth)
    stmt = stmt.on_conflict_do_update(
        index_elements=["endpoint"],
        set_={"p256dh": stmt.excluded.p256dh, "auth": stmt.excluded.auth},
    )
    await session.execute(stmt)
    await session.commit()


async def delete_subscription(session: AsyncSession, endpoint: str) -> None:
    await session.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
    await session.commit()


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    url: str
    # Same tag replaces rather than stacks — one per highlight, so two TDs are two alerts.
    tag: str

    def to_json(self) -> str:
        return json.dumps(
            {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag}
        )


def _vapid_subject() -> str:
    """The VAPID `sub` claim. Apple insists on an https: or mailto: value, and the app's
    own tailnet URL (`GRIDIRON_BASE_URL`) is https in every real deployment."""
    base_url = get_settings().gridiron_base_url
    return base_url if base_url.startswith("https://") else "mailto:gridiron@localhost"


def _send_one(subscription: PushSubscription, payload: str, private_raw: str) -> int:
    """One blocking send; returns the push service's HTTP status."""
    # A fresh claims dict per send: pywebpush writes `aud` (the endpoint's origin) into
    # the dict it's given, and a shared one would carry Apple's origin to Google.
    claims: dict[str, str | int] = {
        "sub": _vapid_subject(),
        "exp": int(time.time()) + TOKEN_SECONDS,
    }
    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=Vapid.from_raw(private_raw.encode("ascii")),
            vapid_claims=claims,
            ttl=TTL_SECONDS,
            headers={"Urgency": "high"},
            timeout=SEND_TIMEOUT_SECONDS,
        )
    except WebPushException as exc:
        if exc.response is None:
            raise
        response = exc.response
    if response.status_code >= 300:
        # The body is the only diagnosis a push service gives (Apple: `BadJwtToken`, ...).
        logger.warning(
            "push: %s answered %d: %s",
            urlparse(subscription.endpoint).hostname,
            response.status_code,
            response.text[:300],
        )
    return response.status_code


async def deliver(session: AsyncSession, message: Message) -> int:
    """Send `message` to every subscription. Returns how many accepted it. A subscription
    its push service has forgotten (404/410) is deleted; nothing here raises."""
    # Key first: a regenerated key deletes every subscription, and those must not be sent to.
    private_raw = await get_private_key(session)
    subscriptions = list((await session.execute(select(PushSubscription))).scalars())
    if not subscriptions:
        return 0
    payload = message.to_json()
    now = datetime.now(UTC).replace(tzinfo=None)

    delivered = 0
    for subscription in subscriptions:
        try:
            status = await asyncio.to_thread(_send_one, subscription, payload, private_raw)
        except Exception:
            logger.exception("push: send to %s failed", urlparse(subscription.endpoint).hostname)
            continue
        if status in (404, 410):
            await session.delete(subscription)
        elif status < 300:
            subscription.last_success_at = now
            delivered += 1
    await session.commit()
    return delivered


_HEADLINES = {"touchdown": "Touchdown", "big_play": "Big play"}
_PLAY_NOUNS = {
    "pass_td": "passing TD",
    "rush_td": "rushing TD",
    "rec_td": "receiving TD",
    "pass_cmp_40p": "completion",
    "rush_40p": "run",
    "rec_40p": "catch",
}


def describe_play(stat_key: str, yards: int | None) -> str:
    """Mirrors `describePlay` in `frontend/src/api/highlights.ts`."""
    noun = _PLAY_NOUNS.get(stat_key, "play")
    if yards is not None:
        return f"{yards}-yd {noun}"
    return f"40+ yd {noun}" if stat_key.endswith("_40p") else noun[0].upper() + noun[1:]


def highlight_message(highlight: PlayerHighlight, player_name: str, more: int = 0) -> Message:
    body = describe_play(highlight.stat_key, highlight.yards)
    if highlight.stat_line:
        body = f"{body} · {highlight.stat_line}"
    if more:
        body = f"{body} (+{more} more)"
    return Message(
        title=f"{_HEADLINES.get(highlight.kind, 'Highlight')}! {player_name}",
        body=body,
        # The app plays the in-app celebration for it on open (see api/highlights.ts).
        url=f"/?highlight={highlight.id}",
        tag=f"highlight-{highlight.id}",
    )


async def notify_highlights(session: AsyncSession, highlights: list[PlayerHighlight]) -> int:
    """Push the newest highlights from one detector run. Never raises: a push service
    being down must not fail `refresh_player_stats`."""
    if not highlights:
        return 0
    try:
        names = dict(
            (
                await session.execute(
                    select(Player.id, Player.name).where(
                        Player.id.in_({h.player_id for h in highlights})
                    )
                )
            ).all()
        )
        shown = highlights[:MAX_PER_RUN]
        more = len(highlights) - len(shown)
        delivered = 0
        for index, highlight in enumerate(shown):
            message = highlight_message(
                highlight,
                names.get(highlight.player_id, "Your starter"),
                more=more if index == len(shown) - 1 else 0,
            )
            delivered += await deliver(session, message)
        return delivered
    except Exception:
        logger.exception("push: notify_highlights failed")
        await session.rollback()
        return 0
