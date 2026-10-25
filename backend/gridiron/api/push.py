"""`/api/push/*` — Web Push opt-in for the Settings card (add-push-notifications).

- `GET  /api/push/vapid-public-key` — the `applicationServerKey` to subscribe with.
- `POST /api/push/subscriptions` — save (upsert) this browser's subscription.
- `DELETE /api/push/subscriptions` — forget it (the toggle turned off).
- `POST /api/push/test` — send a sample to every subscription, to prove the path end to end.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.db import get_session
from backend.gridiron.models import PushSubscription
from backend.gridiron.services import push

router = APIRouter(prefix="/api/push", tags=["push"])


class VapidPublicKey(BaseModel):
    public_key: str


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    """`PushSubscription.toJSON()` as the browser produces it (extra fields ignored)."""

    endpoint: str
    keys: SubscriptionKeys


class SubscriptionRef(BaseModel):
    endpoint: str


class TestResult(BaseModel):
    subscriptions: int
    delivered: int


@router.get("/vapid-public-key", response_model=VapidPublicKey)
async def get_vapid_public_key(session: AsyncSession = Depends(get_session)) -> VapidPublicKey:
    return VapidPublicKey(public_key=await push.get_public_key(session))


@router.post("/subscriptions", status_code=204)
async def save_subscription(
    body: SubscriptionIn, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await push.save_subscription(session, body.endpoint, body.keys.p256dh, body.keys.auth)
    except push.InvalidSubscriptionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_endpoint", "message": "not a known push service"},
        ) from exc


@router.delete("/subscriptions", status_code=204)
async def delete_subscription(
    body: SubscriptionRef, session: AsyncSession = Depends(get_session)
) -> None:
    await push.delete_subscription(session, body.endpoint)


@router.post("/test", response_model=TestResult)
async def send_test(session: AsyncSession = Depends(get_session)) -> TestResult:
    count = (await session.execute(select(func.count(PushSubscription.id)))).scalar_one()
    delivered = await push.deliver(
        session,
        push.Message(
            title="Touchdown! (test)",
            body="Notifications from GridIron are working.",
            url="/settings",
            tag="gridiron-test",
        ),
    )
    return TestResult(subscriptions=count, delivered=delivered)
