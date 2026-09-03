"""httpx client + matcher/mapper/upsert for Sleeper's public projection feed.

Fourth upstream in this codebase, and the only one that serves data about players in
leagues the user does not belong to. No credentials, no OAuth, no cookies.

Two endpoints:

    https://api.sleeper.app/v1/players/nfl                  -- the player dump (~14 MB)
    https://api.sleeper.com/projections/nfl/{season}[/{wk}] -- the projections

`company` on every projection row reads `"rotowire"`: Sleeper is relaying Rotowire's
projections, which is a genuine commercial product given away here. That makes this a
better single number than the platform's own, and it is NOT a consensus of many experts —
it does not close the expert-rankings gap, it sidesteps it.

**Both endpoints are undocumented.** `docs.sleeper.com` covers leagues, rosters and
users; the projections host is not in it. Same risk class as the ESPN endpoints this app
already depends on, and it is handled the same way: fail soft, log, keep the last good
rows.

Matching is the hard part of this module, so it is measured rather than assumed. Against
this install's 194 rostered players:

    tier 1  espn_id from the player dump ....  61   (32%)
    tier 2  normalized name + NFL team ......  118  (61%)
    tier 3  D/ST by team abbreviation .......  15   (8%)
                                              ----
                                              194  (100%)

The surprise is tier 2 doing most of the work. Sleeper's `espn_id` coverage is patchy for
anyone drafted recently — Travis Etienne Jr., Kyle Pitts Sr. and Tank Dell all lack one —
so an id-only matcher would have reached under a third of a roster.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import League, Player
from backend.gridiron.models import PlayerProjection as PlayerProjectionRow
from backend.gridiron.services import cache
from backend.gridiron.services.draft_board import normalize_name

logger = logging.getLogger("uvicorn.error")

PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
PROJECTIONS_BASE = "https://api.sleeper.com/projections/nfl"

SOURCE = "rotowire"

# The player dump is ~14 MB and changes when someone signs, not when someone is
# projected. Cached through `http_cache` like every other upstream payload.
PLAYERS_TTL = timedelta(hours=24)

# `week = 0` is the season-long scope. See `models/player_projections.py`.
SEASON_SCOPE = 0

# Sleeper's `position` for a team defense. Our vocabulary calls it DST.
SLEEPER_DST_POSITION = "DEF"


class SleeperClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        # A browser-ish UA: a bare urllib/python User-Agent gets a 403 from this host,
        # while httpx's default is accepted. Set explicitly so a future default change
        # doesn't silently break the feed.
        self._http = http_client or httpx.AsyncClient(
            timeout=60, headers={"User-Agent": "GridIron/1.0 (self-hosted fantasy dashboard)"}
        )
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_players(self, session: AsyncSession) -> dict:
        """The full player dump, served from `http_cache` when fresh."""
        entry = await cache.get(session, "sleeper", "players", None)
        if entry is not None and not entry.is_expired:
            return json.loads(entry.raw_json)

        response = await self._http.get(PLAYERS_URL)
        response.raise_for_status()
        raw = response.text
        expires_at = datetime.now(UTC).replace(tzinfo=None) + PLAYERS_TTL
        await cache.set(session, "sleeper", "players", None, raw, expires_at)
        return json.loads(raw)

    async def get_projections(self, season: int, week: int | None) -> list[dict]:
        """`week=None` returns season-long totals; an int returns that scoring period."""
        path = (
            f"{PROJECTIONS_BASE}/{season}"
            if week is None
            else f"{PROJECTIONS_BASE}/{season}/{week}"
        )
        response = await self._http.get(path, params={"season_type": "regular"})
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []


# --------------------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------------------


def bridge_espn_athlete_ids(dump: dict, players: list[Player]) -> int:
    """Fill in `players.espn_athlete_id` for players whose own id isn't an ESPN one.

    The reason this lives in the Sleeper module: its dump is the only place in this
    codebase carrying `espn_id` and `yahoo_id` on the same record, which is exactly the
    hop a Yahoo-sourced player needs to reach ESPN's public injury API.

    Returns the number of rows changed. ESPN players are skipped — their athlete id is
    already inside their own `id` — and so are defenses, which Sleeper keys by team
    abbreviation rather than by athlete.
    """
    by_yahoo_id = {
        str(p["yahoo_id"]): str(p["espn_id"])
        for p in dump.values()
        if p.get("yahoo_id") and p.get("espn_id")
    }
    changed = 0
    for player in players:
        if player.platform == "espn" or player.position == "DST":
            continue
        espn_id = by_yahoo_id.get(player.platform_id.removeprefix("p-"))
        if espn_id and player.espn_athlete_id != espn_id:
            player.espn_athlete_id = espn_id
            changed += 1
    return changed


class PlayerIndex:
    """The three lookup tables the matcher consults, in tier order."""

    def __init__(self, dump: dict, projections: list[dict]) -> None:
        by_sleeper_id = {row["player_id"]: row for row in projections}

        # Tier 1: our ESPN id -> a projection row, via the dump's `espn_id`.
        self.by_espn_id: dict[str, dict] = {}
        for sleeper_id, player in dump.items():
            espn_id = player.get("espn_id")
            if espn_id and sleeper_id in by_sleeper_id:
                self.by_espn_id[str(espn_id)] = by_sleeper_id[sleeper_id]

        # Tier 2: (normalized name, NFL team) -> a projection row.
        #
        # Ambiguity is DROPPED, not resolved. A measured check of a full week's feed
        # found zero colliding keys among players with a real team, but the guard stays:
        # attaching one player's projection to another is worse than showing none, and it
        # would be invisible once the number is on screen.
        named: dict[tuple[str, str], dict | None] = {}
        for row in projections:
            player = row.get("player") or {}
            team = player.get("team")
            if not team:
                # 6,617 of ~9,400 rows are teamless — free agents and practice squad.
                # They must not be indexed: our own players carry `nfl_team="FA"`, and
                # letting those two notions of "no team" meet would match on name alone.
                continue
            key = (
                normalize_name(f"{player.get('first_name', '')} {player.get('last_name', '')}"),
                team,
            )
            named[key] = None if key in named else row
        self.by_name_team = {k: v for k, v in named.items() if v is not None}

        # Tier 3: team abbreviation -> that team's defense.
        self.by_dst_team: dict[str, dict] = {}
        for row in projections:
            player = row.get("player") or {}
            if player.get("position") != SLEEPER_DST_POSITION:
                continue
            team = player.get("team") or row.get("player_id")
            if team:
                self.by_dst_team[team] = row

    def find(self, player: Player) -> tuple[dict, str] | None:
        """The projection row for `player`, plus which tier found it."""
        if player.platform == "espn":
            row = self.by_espn_id.get(player.platform_id.removeprefix("p-"))
            if row is not None:
                return row, "espn_id"

        if player.position == "DST":
            row = self.by_dst_team.get(player.nfl_team)
            if row is not None:
                return row, "dst_team"
            return None

        if player.nfl_team and player.nfl_team != "FA":
            row = self.by_name_team.get((normalize_name(player.name), player.nfl_team))
            if row is not None:
                return row, "name_team"
        return None


# --------------------------------------------------------------------------------------
# Mapping + upsert
# --------------------------------------------------------------------------------------


def map_projection(
    player_id: str,
    row: dict,
    *,
    season: int,
    week: int,
    match_tier: str,
    fetched_at: datetime,
) -> PlayerProjectionRow:
    stats = row.get("stats") or {}
    return PlayerProjectionRow(
        player_id=player_id,
        season=season,
        week=week,
        source=SOURCE,
        pts_ppr=stats.get("pts_ppr"),
        pts_half_ppr=stats.get("pts_half_ppr"),
        pts_std=stats.get("pts_std"),
        stats_json=json.dumps(stats, sort_keys=True),
        match_tier=match_tier,
        fetched_at=fetched_at,
    )


async def _season_and_week(session: AsyncSession) -> tuple[int, int]:
    from backend.gridiron.services.fantasy_service import _current_season

    league = (
        (await session.execute(select(League).order_by(League.season.desc()))).scalars().first()
    )
    if league is None:
        return _current_season(), 1
    return league.season, league.current_week or 1


async def fetch_and_upsert(
    session: AsyncSession, client: SleeperClient | None = None
) -> str | None:
    """Refresh weekly AND season-long projections for every player we know about.

    Two upstream calls plus a (usually cached) player dump, regardless of roster size —
    the feed is served whole, so there is nothing to fan out over.
    """
    owns_client = client is None
    client = client or SleeperClient()
    fetched_at = datetime.now(UTC).replace(tzinfo=None)
    try:
        season, week = await _season_and_week(session)
        dump = await client.get_players(session)
        players = list((await session.execute(select(Player))).scalars().all())
        bridged = bridge_espn_athlete_ids(dump, players)

        total = 0
        tiers: dict[str, int] = {}
        for scope_week, request_week in ((week, week), (SEASON_SCOPE, None)):
            rows = await client.get_projections(season, request_week)
            index = PlayerIndex(dump, rows)
            for player in players:
                found = index.find(player)
                if found is None:
                    continue
                row, tier = found
                await session.merge(
                    map_projection(
                        player.id,
                        row,
                        season=season,
                        week=scope_week,
                        match_tier=tier,
                        fetched_at=fetched_at,
                    )
                )
                total += 1
                if scope_week == week:
                    tiers[tier] = tiers.get(tier, 0) + 1
        await session.commit()
    except httpx.HTTPError as exc:
        return f"sleeper projections unavailable: {type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            await client.aclose()

    matched = sum(tiers.values())
    logger.info(
        "refresh_projections season=%d week=%d players=%d matched=%d rows=%d bridged=%d tiers=%s",
        season,
        week,
        len(players),
        matched,
        total,
        bridged,
        tiers,
    )
    if players and matched == 0:
        # Never silently serve an empty projection column: a total miss means the feed
        # shape changed or the season/week is wrong, and both are worth surfacing on the
        # refresh-runs row rather than looking like "no data this week".
        return f"sleeper projections matched 0 of {len(players)} players"
    return None
