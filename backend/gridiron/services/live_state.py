"""Live-state classifier (task 8.1) + the module-level "current live_state" store that
`refresh_nfl_state` (scheduler.py) updates and `build_meta`/`GET /api/events` read.

`classify` is intentionally pure (no I/O) so the state matrix is trivial to unit test;
`user_nfl_teams` is the one small DB query it needs, kept separate on purpose.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import League, Player, RosterSlot, Team
from backend.gridiron.schemas.common import LiveState
from backend.gridiron.schemas.live_nfl_games import LiveNflGame

# Bench/IR don't count toward "the user has a rostered player in this game" — mirrors
# fantasy_service.STARTER_EXCLUDED_SLOTS. Duplicated (not imported) so this module stays
# a leaf dependency of fantasy_service, not the other way around.
_STARTER_EXCLUDED_SLOTS = ("BN", "IR")

# A game kicking off within this window, but not yet live, still counts as "game_day" —
# the adaptive scheduler should already be ramping up cadence ahead of kickoff rather
# than waiting for the first "in" tick.
PRE_GAME_WINDOW = timedelta(hours=2)

# Single-process, single-user app (design.md D1): the current live_state is deliberately
# in-memory, not persisted — a restart clears it back to "off_day" and the next
# `refresh_nfl_state` tick (30s, task 8.2) re-derives the real value.
_current_live_state: LiveState = "off_day"


def get_current_live_state() -> LiveState:
    """The live_state as of the most recent `refresh_nfl_state` tick. Feeds
    `fantasy_service.build_meta` and `GET /api/events`'s connect-time replay."""
    return _current_live_state


def set_current_live_state(state: LiveState) -> None:
    global _current_live_state
    _current_live_state = state


def reset_state() -> None:
    """Reset the module-level current live_state back to its default (test isolation)."""
    global _current_live_state
    _current_live_state = "off_day"


async def user_nfl_teams(session: AsyncSession) -> set[str]:
    """NFL team abbreviations with at least one non-bench player rostered on a user team
    in an enabled league, for that league's own current week.

    Feeds `classify`'s "does this in-progress game involve a team the user has a
    rostered starter on" check.
    """
    rows = (
        (
            await session.execute(
                select(Player.nfl_team)
                .join(RosterSlot, RosterSlot.player_id == Player.id)
                .join(Team, Team.id == RosterSlot.team_id)
                .join(League, League.id == Team.league_id)
                .where(
                    Team.is_user_team.is_(True),
                    League.is_enabled.is_(True),
                    RosterSlot.week == League.current_week,
                    RosterSlot.slot.not_in(_STARTER_EXCLUDED_SLOTS),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _is_today_or_soon(kickoff_at: datetime, now: datetime) -> bool:
    """ "Today" per the codebase's existing naive-UTC datetime convention (every
    `created_at`/`run_at`/etc. column is naive UTC, no per-user timezone handling
    anywhere yet) — a real "local date" would need a stored user timezone, which is out
    of scope here."""
    if kickoff_at.date() == now.date():
        return True
    return now <= kickoff_at <= now + PRE_GAME_WINDOW


def classify(games: list[LiveNflGame], user_nfl_teams: set[str], now: datetime) -> LiveState:
    """ "live" when any in-progress game involves an NFL team the user has a rostered
    (non-bench) starter on; else "game_day" when any game kicks off today or within
    `PRE_GAME_WINDOW`; else "off_day"."""
    for game in games:
        if game.state == "in" and (
            game.home_team in user_nfl_teams or game.away_team in user_nfl_teams
        ):
            return "live"
    if any(_is_today_or_soon(game.kickoff_at, now) for game in games):
        return "game_day"
    return "off_day"
