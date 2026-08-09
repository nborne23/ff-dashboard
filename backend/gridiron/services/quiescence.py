"""Off-season quiescence (task 11.7).

`refresh_nfl_state` polls ESPN's public scoreboard every 30s; `refresh_fantasy` re-syncs
every 30 min at its slowest in-season cadence. Neither of those is worth doing for months
at a stretch during the NFL off-season, when the scoreboard simply has nothing to report.

The signal used here is deliberately simple and needs no new upstream call: every
`refresh_nfl_state` tick already fetches the scoreboard, so `record_kickoffs_seen` just
remembers the newest `kickoff_at` it has ever seen across those fetches (in an
`app_settings` KV row, `NEWEST_KICKOFF_KEY`), *never moving it backwards*. During the
season the scoreboard always lists the upcoming week's games ahead of kickoff, so this
watermark constantly advances into the near future — `is_off_season` reads as `False`.
Once the season ends, the scoreboard stops advancing it (no new games are listed), so the
watermark freezes at the season's last kickoff and — as real time keeps moving —
eventually falls more than `OFF_SEASON_THRESHOLD` behind `now`. The moment preseason
games reappear on the scoreboard the watermark jumps forward again and cadence snaps back
to normal, with no separate "is it August yet" calendar logic needed.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import AppSetting
from backend.gridiron.schemas.live_nfl_games import LiveNflGame

NEWEST_KICKOFF_KEY = "newest_kickoff_seen"

# "Shown no games for > 7 days" per task 11.7's wording.
OFF_SEASON_THRESHOLD = timedelta(days=7)

# Backed-off cadences (task 11.7): refresh_fantasy drops to once a day, refresh_nfl_state
# backs off to hourly — still enough to notice the season starting back up without
# polling all day for nothing in between.
OFF_SEASON_FANTASY_INTERVAL_SECONDS = 24 * 60 * 60
OFF_SEASON_NFL_STATE_INTERVAL_SECONDS = 60 * 60


async def get_newest_kickoff_seen(session: AsyncSession) -> datetime | None:
    """The persisted watermark, or `None` when `refresh_nfl_state` has never seen a
    game (a totally fresh database, or a scoreboard that's been empty since boot)."""
    row = await session.get(AppSetting, NEWEST_KICKOFF_KEY)
    if row is None:
        return None
    return datetime.fromisoformat(row.value)


async def record_kickoffs_seen(session: AsyncSession, games: list[LiveNflGame]) -> None:
    """Advance the stored watermark from this tick's scoreboard fetch, never moving it
    backwards. A no-op when `games` is empty — an empty scoreboard fetch is exactly the
    "nothing new to report" case `is_off_season` needs to see, so it must not touch the
    watermark at all."""
    if not games:
        return
    newest = max(game.kickoff_at for game in games)

    row = await session.get(AppSetting, NEWEST_KICKOFF_KEY)
    if row is None:
        session.add(AppSetting(key=NEWEST_KICKOFF_KEY, value=newest.isoformat()))
        await session.commit()
        return
    if newest > datetime.fromisoformat(row.value):
        row.value = newest.isoformat()
        await session.commit()


def is_off_season(now: datetime, newest_kickoff_seen: datetime | None) -> bool:
    """Pure decision function (task 11.7 — unit-tested directly with fake dates).

    `None` (the watermark has never been set — a fresh database, or `refresh_nfl_state`
    simply hasn't ticked yet) reads as *not* off-season: there's no evidence either way
    yet, and defaulting to the normal in-season cadence is the safer/less-surprising
    choice for a freshly-booted app (and keeps the pre-existing off_day-cadence tests,
    which never seed this watermark, passing unchanged). Off-season is something we only
    conclude from positive evidence: a watermark that's gone stale.
    """
    if newest_kickoff_seen is None:
        return False
    return (now - newest_kickoff_seen) > OFF_SEASON_THRESHOLD
