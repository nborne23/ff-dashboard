"""`PlayerInjuryReport` / `PlayerInjuryData` — add-player-health's detail payload."""

from datetime import datetime

from pydantic import BaseModel


class PlayerInjuryReport(BaseModel):
    """ESPN's own report on one player, as stored by `refresh_injuries`.

    Every field but `fetched_at` is optional: ESPN routinely files a report carrying only
    a status and a date (a practice-report entry), and fills in `details`/comments later.
    """

    status: str | None = None
    injury_type: str | None = None
    location: str | None = None
    detail: str | None = None
    side: str | None = None
    # ESPN publishes this as a plain `YYYY-MM-DD` string with no timezone, and it is an
    # estimate that moves — kept as the string it is rather than parsed into a datetime
    # that would imply a precision it doesn't have.
    return_date: str | None = None
    short_comment: str | None = None
    long_comment: str | None = None
    reported_at: datetime | None = None
    fetched_at: datetime


class PlayerInjuryData(BaseModel):
    """Payload of `GET /api/players/{player_id}/injury`.

    `report is None` is the ordinary answer, not an error: most players are healthy, and
    ESPN returns `count: 0` for them.
    """

    player_id: str
    # The normalized designation from the fantasy platform (`players.injury_status`) —
    # what the badge renders. Always present even when `report` is None.
    injury_status: str | None
    report: PlayerInjuryReport | None
    # False for players this app cannot look up on ESPN's athlete API at all: D/ST rows
    # (synthetic negative ids) and Yahoo-sourced players (no ESPN athlete id). Lets the
    # panel say "not available for this player" instead of "no injury".
    detail_supported: bool
