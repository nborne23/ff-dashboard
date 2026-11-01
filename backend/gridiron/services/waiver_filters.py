"""The Waivers screen's filter sheet: which players are listed, and in what order.

Kept out of `fantasy_service.get_waivers` so the ranking read stays one function and the
filter vocabulary (the `Literal`s the API validates against) lives in one place.

Every filter is applied server-side, before the `limit` cut. The list is a shortlist of
the top 50 by upgrade; filtering that shortlist in the browser would answer "Waivers
Only" with the two waiver players who happened to rank in the top 50, not with the
league's waiver wire.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

StatusFilter = Literal["available", "free_agents", "waivers", "all"]
SortKey = Literal["upgrade", "upgrade_week", "owned"]

# Which `player_pool_entries.status` values each STATUS option reads from the pool.
#
# "all" reads the same claimable rows as "available"; its rostered players come from
# `roster_slots` instead (see `get_waivers`). Two reasons: Yahoo's pool is fetched
# available-only and holds no rostered player at all, and ESPN's ONTEAM rows carry
# ESPN's numeric team id rather than one this app can name the owner from.
POOL_STATUSES: dict[StatusFilter, tuple[str, ...]] = {
    "available": ("FREEAGENT", "WAIVERS"),
    "free_agents": ("FREEAGENT",),
    "waivers": ("WAIVERS",),
    "all": ("FREEAGENT", "WAIVERS"),
}

# NFL game days are Eastern-time days. Thursday Night Football kicks off at 8:15pm ET,
# which is already Friday in UTC — bucketing by the UTC date would file TNF under a
# "Friday" option that no one is looking for.
NFL_TZ = ZoneInfo("America/New_York")

# Eligibility for a rostered player with no pool row (every Yahoo rostered player — the
# pool is fetched available-only). Without it the player would contest no slot and
# carry a null upgrade. A position's own slot plus FLEX covers every standard lineup;
# the league-specific cases a pool row would add (superflex `OP`, TE-premium) are the
# ones this approximation knowingly misses.
_FLEX_POSITIONS = {"RB", "WR", "TE"}


def fallback_eligibility(position: str) -> list[str]:
    return [position, "FLEX"] if position in _FLEX_POSITIONS else [position]


def game_date(kickoff_utc: datetime) -> date:
    """The Eastern-time calendar day of a naive-UTC kickoff."""
    return kickoff_utc.replace(tzinfo=UTC).astimezone(NFL_TZ).date()


@dataclass(frozen=True)
class ScheduledGame:
    kickoff_at: datetime  # naive UTC, as `live_nfl_games` stores it
    state: str  # "pre" | "in" | "post"


def week_schedule(
    rows: Iterable[tuple[str, str, str, datetime]], normalize: Callable[[str], str]
) -> dict[str, ScheduledGame]:
    """NFL team -> its game this week, from `live_nfl_games` `(home, away, state, kickoff)`.

    That table holds several weeks at once — `nfl_scoreboard.upsert_games` never deletes a
    row — so per team only the newest kickoff counts, and of those only the ones within six
    days of the newest kickoff overall. A team on bye has nothing newer than last week's
    game, and last week's Monday night is seven days before this week's.
    """
    latest: dict[str, ScheduledGame] = {}
    for home, away, state, kickoff in rows:
        for abbr in (home, away):
            if not abbr:
                continue
            team = normalize(abbr)
            seen = latest.get(team)
            if seen is None or kickoff > seen.kickoff_at:
                latest[team] = ScheduledGame(kickoff_at=kickoff, state=state)
    if not latest:
        return {}
    cutoff = max(game.kickoff_at for game in latest.values()) - timedelta(days=6)
    return {team: game for team, game in latest.items() if game.kickoff_at >= cutoff}


def remaining_game_days(schedule: dict[str, ScheduledGame]) -> list[date]:
    """The days with at least one game not yet final, ascending. A day whose games are all
    over is not offered: "available players playing Thursday" is a question about
    Thursday's lineup lock, which on Saturday has already happened."""
    return sorted({game_date(g.kickoff_at) for g in schedule.values() if g.state != "post"})


@dataclass
class CandidateRow:
    """One listable player, from either source: a pool entry (claimable) or a roster slot
    (rostered, for "All Players" and "Show My Team"). Normalized here so the ranking loop
    doesn't care which."""

    player: object  # models.Player — typed loosely to keep this module model-free
    status: str
    on_team_id: str | None
    percent_owned: float | None
    percent_started: float
    pool_season_proj: float | None
    eligible: list[str]
    waiver_clears: date | None = None
    is_mine: bool = False
    rostered_by: str | None = None


def sort_key(
    sort: SortKey,
    *,
    delta: float | None,
    season_points: float | None,
    week_delta: float | None,
    week_points: float | None,
    percent_owned: float | None,
) -> tuple:
    """Biggest first on the chosen axis; rows with nothing to rank on last. The season
    upgrade breaks ties on every axis, then the projection, so equal rows order by the
    better player."""

    def desc(value: float | None) -> tuple[bool, float]:
        return (value is None, -(value if value is not None else 0.0))

    season = (*desc(delta), *desc(season_points))
    if sort == "upgrade_week":
        return (*desc(week_delta), *desc(week_points), *season)
    if sort == "owned":
        return (*desc(percent_owned), *season)
    return season
