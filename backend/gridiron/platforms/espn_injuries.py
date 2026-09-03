"""httpx client + mapper/upsert for ESPN's public NFL injury-report API (add-player-health).

Third ESPN surface in this codebase, and the distinction matters:

- `platforms/espn/client.py` — the AUTHENTICATED fantasy API (SWID/espn_s2, per-league).
  It supplies the coarse designation (`Q`/`O`/`IR`) that `players.injury_status` holds.
- `platforms/nfl_scoreboard.py` — the public site API, for raw NFL game state.
- this module — the public CORE api, for what is actually wrong with a player: body part,
  side, surgery vs rehab, projected return, and ESPN's own written update.

No credentials. Two things about the upstream shape are load-bearing:

1. **The season is part of the path and it is not optional.** The same athlete returns
   `count: 0` under `seasons/2025` and a full report under `seasons/2026`. The season comes
   from the persisted leagues, never a literal.
2. **`count: 0` is the healthy answer**, returned constantly. It is not an error and is not
   logged as one — it clears any stale row instead.
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import League, Player
from backend.gridiron.models import PlayerInjury as PlayerInjuryRow

logger = logging.getLogger("uvicorn.error")

CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"

# Designations worth a detail fetch. `ACTIVE` and `None` are excluded: ESPN answers
# `count: 0` for a healthy player, so sweeping them would be ~900 requests for nothing.
FETCHABLE_STATUSES = ("Q", "D", "O", "IR", "PUP", "DTD", "SUSP", "NFI")

# Politeness/blast-radius ceiling on one job run. This install's non-healthy set is ~130
# players; the cap exists so a data anomaly (every player marked `O` by a mis-parse) can't
# turn one tick into a thousand requests against a free public endpoint.
MAX_ATHLETES_PER_RUN = 400


class EspnInjuriesClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=15)
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_injuries(self, season: int, athlete_id: str) -> dict:
        response = await self._http.get(
            f"{CORE_API_BASE}/seasons/{season}/athletes/{athlete_id}/injuries",
            params={"limit": 5},
        )
        response.raise_for_status()
        return response.json()


def espn_athlete_id(player_id: str, bridged_id: str | None = None) -> str | None:
    """The ESPN athlete id to query, or `None` when there is nothing to ask about.

    `bridged_id` is `players.espn_athlete_id` — the Sleeper-supplied cross-reference that
    gives a YAHOO-sourced player an ESPN athlete id. Without it a Yahoo roster could see
    injury designations but never the detail behind them.

    One id class is still rejected rather than tried-and-404'd: D/ST rows, whose ESPN ids
    are synthetic and NEGATIVE (`"espn:p--16007"`). A team defense is not an athlete and
    has no injury report — and the bridge does not rescue it, because Sleeper keys
    defenses by team abbreviation rather than by athlete.
    """
    platform, _, rest = player_id.partition(":")
    if platform == "espn":
        athlete_id = rest.removeprefix("p-")
        if athlete_id.isdigit():
            return athlete_id
        # A negative (D/ST) id is never bridgeable; fall through to None rather than
        # letting a stale bridged value resurrect it.
        return None
    if bridged_id and bridged_id.isdigit():
        return bridged_id
    return None


def detail_supported(player_id: str, bridged_id: str | None = None) -> bool:
    return espn_athlete_id(player_id, bridged_id) is not None


def _parse_reported_at(raw_date: str | None) -> datetime | None:
    """ESPN sends `"2026-08-13T15:11Z"` — normalize to the codebase's naive-UTC convention."""
    if not raw_date:
        return None
    try:
        parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable espn injury date: %r", raw_date)
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def map_injury(player_id: str, payload: dict, *, fetched_at: datetime) -> PlayerInjuryRow | None:
    """The newest report in `payload`, or `None` when ESPN has nothing on this player.

    ESPN orders `items` newest-first and this keeps only the head — the panel answers
    "what is wrong with him now", and the older entries are the same injury restated as it
    progressed through the week.
    """
    items = payload.get("items") or []
    if not items:
        return None
    item = items[0]
    details = item.get("details") or {}
    return PlayerInjuryRow(
        player_id=player_id,
        report_id=str(item["id"]) if item.get("id") is not None else None,
        status=item.get("status"),
        injury_type=details.get("type"),
        location=details.get("location"),
        detail=details.get("detail"),
        side=details.get("side"),
        return_date=details.get("returnDate"),
        short_comment=item.get("shortComment"),
        long_comment=item.get("longComment"),
        reported_at=_parse_reported_at(item.get("date")),
        fetched_at=fetched_at,
    )


async def _season(session: AsyncSession) -> int:
    """The season to query, from the persisted leagues.

    Imported lazily to keep this module free of a `fantasy_service` import cycle —
    `fantasy_service` already imports the platform packages.
    """
    from backend.gridiron.services.fantasy_service import _current_season

    season = (
        (await session.execute(select(League.season).order_by(League.season.desc())))
        .scalars()
        .first()
    )
    return season or _current_season()


async def _players_to_sweep(session: AsyncSession) -> list[Player]:
    rows = (
        (
            await session.execute(
                select(Player)
                .where(Player.injury_status.in_(FETCHABLE_STATUSES))
                .order_by(Player.id)
                .limit(MAX_ATHLETES_PER_RUN)
            )
        )
        .scalars()
        .all()
    )
    return [row for row in rows if detail_supported(row.id, row.espn_athlete_id)]


async def fetch_and_upsert(
    session: AsyncSession, client: EspnInjuriesClient | None = None
) -> str | None:
    """Refresh stored reports for every non-healthy player. Returns an error summary or `None`.

    One failing athlete never fails the run: the endpoint is a free public service with no
    SLA, and a 404 on one id is not a reason to leave the other 129 players stale.

    Two known limits, neither worth engineering around at this scale:

    - A player who RECOVERS between runs (Q -> ACTIVE) drops out of `_players_to_sweep`,
      so their `player_injuries` row is never revisited and goes stale. The UI can't show
      it — `isNoteworthy` gates the badge on the fantasy status, and the panel only opens
      from a badge — but `GET /api/players/{id}/injury` will serve the old report next to
      an `injury_status` of `ACTIVE`.
    - `MAX_ATHLETES_PER_RUN` is a SQL `LIMIT` applied BEFORE the `detail_supported`
      filter, so it bounds rows considered, not requests issued. A Yahoo-heavy
      non-healthy set therefore covers fewer than the cap suggests. It is a blast-radius
      ceiling, not a coverage guarantee.
    """
    owns_client = client is None
    client = client or EspnInjuriesClient()
    season = await _season(session)
    players = await _players_to_sweep(session)
    fetched_at = datetime.now(UTC).replace(tzinfo=None)

    fetched = 0
    cleared = 0
    failures: list[str] = []
    try:
        for player in players:
            athlete_id = espn_athlete_id(player.id, player.espn_athlete_id)
            assert athlete_id is not None  # `_players_to_sweep` filtered on exactly this
            try:
                payload = await client.get_injuries(season, athlete_id)
            except httpx.HTTPError as exc:
                failures.append(f"{player.id}: {type(exc).__name__}")
                continue
            row = map_injury(player.id, payload, fetched_at=fetched_at)
            if row is None:
                # ESPN dropped the report (player activated). Drop ours too rather than
                # leaving a resolved injury on screen indefinitely.
                await session.execute(
                    delete(PlayerInjuryRow).where(PlayerInjuryRow.player_id == player.id)
                )
                cleared += 1
                continue
            await session.merge(row)
            fetched += 1
        await session.commit()
    finally:
        if owns_client:
            await client.aclose()

    logger.info(
        "refresh_injuries season=%d swept=%d stored=%d cleared=%d failed=%d",
        season,
        len(players),
        fetched,
        cleared,
        len(failures),
    )
    if failures:
        shown = ", ".join(failures[:5])
        suffix = f" (+{len(failures) - 5} more)" if len(failures) > 5 else ""
        return f"{len(failures)} injury fetch(es) failed: {shown}{suffix}"
    return None
