"""`http_cache` get/set/invalidate — the only path upstream JSON responses flow through.

Per design.md D7, read endpoints ALWAYS serve whatever is cached; they never fetch from
Yahoo/ESPN on a miss. This module performs no I/O itself — it is a pure key/value store
keyed by `(platform, endpoint, params_hash)`, with `raw_json` and `expires_at`. Only the
scheduler (a later task) is expected to call `set`.

`get` returns the row even when it's expired — the caller decides what "stale" means for
its use case via `CacheEntry.is_expired`.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import HttpCache

# Task 9.5: a week's upstream data is effectively frozen once it's fully in the past —
# cache it for a full day instead of a platform's short off-day default, to cut needless
# repeat upstream calls for weeks that will never change again.
PAST_WEEK_TTL = timedelta(hours=24)


def select_ttl(week: int, current_week: int | None, default_ttl: timedelta) -> timedelta:
    """Choose the cache TTL for a `week`-scoped roster/matchup fetch (task 9.5).

    `current_week` is the caller's best knowledge of the league's *actual* current week
    (not necessarily the same as `week`, which is whatever was requested). A week only
    counts as safely "past" once at least one full week has elapsed beyond it —
    `current_week == week + 1` is still the week that *just* finished, whose stats can
    still get late corrections, so it keeps the platform's shorter default TTL.

    `current_week=None` (the caller doesn't know / didn't pass one) always keeps the
    default — this is what preserves today's behavior for every existing call site.

    Phase 8: SSE events must never fire for past weeks — once a response is cached under
    `PAST_WEEK_TTL`, there's nothing left to diff against, so the live differ/publisher
    should skip any week where this branch applies.
    """
    if current_week is not None and current_week > week + 1:
        return PAST_WEEK_TTL
    return default_ttl


def params_hash(params: dict | None) -> str:
    """Stable sha256 hex digest of `params`, independent of key order.

    `None` and `{}` hash identically (both normalize to `{}`).
    """
    normalized = params or {}
    payload = json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize to UTC and strip tzinfo, matching how SQLite/aiosqlite reads `DateTime` back."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


@dataclass(frozen=True)
class CacheEntry:
    platform: str
    endpoint: str
    params_hash: str
    raw_json: str
    fetched_at: datetime
    expires_at: datetime
    is_expired: bool


async def get(
    session: AsyncSession,
    platform: str,
    endpoint: str,
    params: dict | None = None,
) -> CacheEntry | None:
    """Fetch the cached row for `(platform, endpoint, params)`, or `None` if never cached."""
    key_hash = params_hash(params)
    row = await session.get(HttpCache, (platform, endpoint, key_hash))
    if row is None:
        return None
    now = _as_naive_utc(datetime.now(UTC))
    return CacheEntry(
        platform=row.platform,
        endpoint=row.endpoint,
        params_hash=row.params_hash,
        raw_json=row.raw_json,
        fetched_at=row.fetched_at,
        expires_at=row.expires_at,
        is_expired=row.expires_at <= now,
    )


async def set(
    session: AsyncSession,
    platform: str,
    endpoint: str,
    params: dict | None,
    raw_json: str,
    expires_at: datetime,
    fetched_at: datetime | None = None,
) -> None:
    """Upsert the cache row for `(platform, endpoint, params_hash)`."""
    key_hash = params_hash(params)
    fetched = _as_naive_utc(fetched_at if fetched_at is not None else datetime.now(UTC))
    expires = _as_naive_utc(expires_at)

    row = await session.get(HttpCache, (platform, endpoint, key_hash))
    if row is None:
        session.add(
            HttpCache(
                platform=platform,
                endpoint=endpoint,
                params_hash=key_hash,
                raw_json=raw_json,
                fetched_at=fetched,
                expires_at=expires,
            )
        )
    else:
        row.raw_json = raw_json
        row.fetched_at = fetched
        row.expires_at = expires
    await session.commit()


async def invalidate(
    session: AsyncSession,
    *,
    platform: str | None = None,
    endpoint: str | None = None,
    params: dict | None = None,
) -> None:
    """Invalidate cache rows, from most to least specific:

    - `invalidate(session, platform=p, endpoint=e, params=params)` — exactly one row.
    - `invalidate(session, platform=p)` — every row for that platform.
    - `invalidate(session)` — the entire cache.

    `endpoint`/`params` are only meaningful alongside `platform`.

    Invalidating sets `expires_at = now()` rather than deleting the row. Per design.md
    D7, read endpoints ALWAYS serve whatever's cached — deleting would turn a live read
    into an empty payload during the window before the next scheduler refresh. Marking
    expired keeps `get` returning the (now stale) data with `is_expired=True` until a
    fresh `set` replaces it. This also matches the platform-integrations spec's
    "Live-game invalidation" scenario, which explicitly sets `expires_at = now()`.
    """
    if endpoint is not None and platform is None:
        raise ValueError("platform is required when endpoint is given")
    if params is not None and endpoint is None:
        raise ValueError("endpoint is required when params is given")

    now = _as_naive_utc(datetime.now(UTC))
    stmt = update(HttpCache).values(expires_at=now)
    if platform is not None:
        stmt = stmt.where(HttpCache.platform == platform)
    if endpoint is not None:
        stmt = stmt.where(HttpCache.endpoint == endpoint)
        stmt = stmt.where(HttpCache.params_hash == params_hash(params))

    await session.execute(stmt)
    await session.commit()
