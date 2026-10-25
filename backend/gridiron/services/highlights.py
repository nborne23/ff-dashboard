"""Touchdown / big-play detection for the user's starters (add-play-highlights).

Wraps the `refresh_player_stats` job: `snapshot` reads the starters' current-week stat
lines before the fetch, `record_new` reads them again after and turns every stat that
went UP into a `player_highlights` row. The stored line from the last tick is the
baseline, so nothing here keeps state in memory and a restart fires nothing twice.

What counts:

- **Touchdowns** — `pass_td`, `rush_td`, `rec_td`. Team defenses are left out: Sleeper's
  DEF `td` is the whole NFL team's touchdown count, offense included.
- **Big plays** — a 40+ yard run, catch, or completion, via Sleeper's `*_40p` counters.
  Those count single plays, which a yardage jump between two ticks two minutes apart
  can't: four short catches on one drive would look the same.

A touchdown and a big play in the same tick are one highlight (the touchdown); a 60-yard
catch that set up a 2-yard TD is still a touchdown story.

What never fires:

- A first reading with nothing recent to compare against: a new week, a fresh install
  (see `snapshot` for the starter whose first line arrives mid-afternoon).
- A baseline older than `STALE_BASELINE`: after the server was down for the second
  half, five touchdowns at once would be a recap, not a celebration.
- A stat going down (a correction), or the same line read twice.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import (
    League,
    Player,
    PlayerHighlight,
    PlayerWeeklyStat,
    RosterSlot,
    Team,
)
from backend.gridiron.platforms import sleeper
from backend.gridiron.schemas.events import DataChangedEvent
from backend.gridiron.services import events

logger = logging.getLogger("uvicorn.error")

# The SSE scope `api/events.ts` maps to the `["highlights"]` query key.
SCOPE = "highlights"

# Counter -> the "longest" stat that gives the play's yards, when this play set it.
TOUCHDOWN_STATS = {"pass_td": "pass_td_lng", "rush_td": "rush_td_lng", "rec_td": "rec_td_lng"}
BIG_PLAY_STATS = {"rush_40p": "rush_lng", "rec_40p": "rec_lng", "pass_cmp_40p": "pass_lng"}

# Five missed live ticks. Long enough to ride out a slow upstream, short enough that a
# real outage resets the baseline instead of replaying the afternoon.
STALE_BASELINE = timedelta(minutes=10)

# Mirrors `fantasy_service.STARTER_EXCLUDED_SLOTS`; see `live_state.py` on why it's copied.
_STARTER_EXCLUDED_SLOTS = ("BN", "IR")


@dataclass(frozen=True)
class Starter:
    player_id: str
    position: str


@dataclass(frozen=True)
class Reading:
    stats: dict[str, float]
    fetched_at: datetime


@dataclass(frozen=True)
class Snapshot:
    season: int
    week: int
    starters: dict[str, Starter]  # keyed by sleeper_id
    readings: dict[str, Reading]  # keyed by sleeper_id; absent = no row yet


@dataclass(frozen=True)
class Detection:
    kind: str  # "touchdown" | "big_play"
    stat_key: str
    ordinal: int
    yards: int | None


def _count(stats: dict[str, float], key: str) -> float:
    return stats.get(key) or 0


def _new_long(before: dict[str, float], after: dict[str, float], key: str) -> int | None:
    """The play's yards, but only when this tick moved the "longest" stat. A 45-yard catch
    after a 57-yarder earlier leaves `rec_lng` at 57, which would be the wrong play."""
    if _count(after, key) > _count(before, key):
        return int(after[key])
    return None


def detect(before: dict[str, float], after: dict[str, float]) -> list[Detection]:
    """Every highlight between two readings of one player's line. Pure."""
    touchdowns = [
        Detection("touchdown", key, int(after[key]), _new_long(before, after, lng))
        for key, lng in TOUCHDOWN_STATS.items()
        if _count(after, key) > _count(before, key)
    ]
    if touchdowns:
        return touchdowns
    return [
        Detection("big_play", key, int(after[key]), _new_long(before, after, lng))
        for key, lng in BIG_PLAY_STATS.items()
        if _count(after, key) > _count(before, key)
    ]


def stat_line(position: str, stats: dict[str, float]) -> str:
    """ "6 rec · 112 yds · 2 TD" — the one line under the name in the celebration."""

    def n(key: str) -> int:
        return int(_count(stats, key))

    if position == "QB":
        parts = [f"{n('pass_cmp')}/{n('pass_att')}", f"{n('pass_yd')} yds", f"{n('pass_td')} TD"]
        if n("rush_td"):
            parts.append(f"{n('rush_td')} rush TD")
        return " · ".join(parts)
    if position == "RB":
        parts = [f"{n('rush_att')} car", f"{n('rush_yd')} yds"]
        if n("rec"):
            parts.append(f"{n('rec')} rec")
    else:
        parts = [f"{n('rec')} rec", f"{n('rec_yd')} yds"]
    touchdowns = n("rush_td") + n("rec_td")
    if touchdowns:
        parts.append(f"{touchdowns} TD")
    return " · ".join(parts)


async def user_starters(session: AsyncSession) -> dict[str, Starter]:
    """Sleeper id -> starter, across every user team in an enabled league, for that
    league's current week. One entry per Sleeper id: the same man on two user teams is one
    touchdown, not two. Players with no `sleeper_id` bridge have no stats to watch."""
    rows = (
        await session.execute(
            select(Player.sleeper_id, Player.id, Player.position)
            .join(RosterSlot, RosterSlot.player_id == Player.id)
            .join(Team, Team.id == RosterSlot.team_id)
            .join(League, League.id == Team.league_id)
            .where(
                Team.is_user_team.is_(True),
                League.is_enabled.is_(True),
                RosterSlot.week == League.current_week,
                RosterSlot.slot.not_in(_STARTER_EXCLUDED_SLOTS),
                Player.sleeper_id.is_not(None),
            )
            .order_by(Player.id)
        )
    ).all()
    starters: dict[str, Starter] = {}
    for sleeper_id, player_id, position in rows:
        starters.setdefault(sleeper_id, Starter(player_id=player_id, position=position))
    return starters


async def _readings(
    session: AsyncSession, season: int, week: int, sleeper_ids: list[str]
) -> dict[str, Reading]:
    # Columns, not entities: the job's session is `expire_on_commit=False` and the upsert
    # in between is Core, so an entity still in the identity map would come back with the
    # BEFORE values and every diff would be empty.
    rows = await session.execute(
        select(
            PlayerWeeklyStat.sleeper_id, PlayerWeeklyStat.stats_json, PlayerWeeklyStat.fetched_at
        ).where(
            PlayerWeeklyStat.season == season,
            PlayerWeeklyStat.week == week,
            PlayerWeeklyStat.sleeper_id.in_(sleeper_ids),
        )
    )
    return {
        sleeper_id: Reading(stats=json.loads(stats_json or "{}"), fetched_at=fetched_at)
        for sleeper_id, stats_json, fetched_at in rows
    }


async def snapshot(session: AsyncSession, now: datetime | None = None) -> Snapshot | None:
    """The starters' current-week lines as they stand now, or None with nobody to watch.

    A starter with no row yet — his game hasn't started, or he hasn't touched the ball —
    gets an empty baseline IF the week's feed was read recently: that read is proof he
    had nothing then, so a first line that already holds a touchdown still fires. With no
    recent read (a new week, a fresh install, an outage) he seeds silently like anyone.
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    season, week = await sleeper._season_and_week(session)
    starters = await user_starters(session)
    if not starters:
        return None
    readings = await _readings(session, season, week, list(starters))
    last_read = (
        await session.execute(
            select(func.max(PlayerWeeklyStat.fetched_at)).where(
                PlayerWeeklyStat.season == season, PlayerWeeklyStat.week == week
            )
        )
    ).scalar_one()
    if last_read is not None and now - last_read <= STALE_BASELINE:
        for sleeper_id in starters:
            readings.setdefault(sleeper_id, Reading(stats={}, fetched_at=last_read))
    return Snapshot(season=season, week=week, starters=starters, readings=readings)


async def record_new(
    session: AsyncSession, before: Snapshot, now: datetime | None = None
) -> list[PlayerHighlight]:
    """Diff the starters' lines against `before`, store what's new, and signal the
    frontend. Returns the rows actually inserted (re-reads collide and return nothing)."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    after = await _readings(session, before.season, before.week, list(before.starters))

    inserted: list[PlayerHighlight] = []
    for sleeper_id, reading in after.items():
        baseline = before.readings.get(sleeper_id)
        if baseline is None or reading.fetched_at == baseline.fetched_at:
            continue
        if now - baseline.fetched_at > STALE_BASELINE:
            continue
        starter = before.starters[sleeper_id]
        line = stat_line(starter.position, reading.stats)
        for found in detect(baseline.stats, reading.stats):
            row = (
                await session.execute(
                    insert(PlayerHighlight)
                    .values(
                        sleeper_id=sleeper_id,
                        player_id=starter.player_id,
                        season=before.season,
                        week=before.week,
                        kind=found.kind,
                        stat_key=found.stat_key,
                        ordinal=found.ordinal,
                        yards=found.yards,
                        stat_line=line,
                        created_at=now,
                    )
                    .on_conflict_do_nothing()
                    .returning(PlayerHighlight)
                )
            ).scalar_one_or_none()
            if row is not None:
                inserted.append(row)
    await session.commit()

    if inserted:
        logger.info("highlights week=%d new=%d", before.week, len(inserted))
        events.publish(DataChangedEvent(scopes=[SCOPE], as_of=now))
    return inserted
