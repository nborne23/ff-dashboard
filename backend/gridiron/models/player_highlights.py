"""Touchdowns and big plays by the user's starters, as they happen (add-play-highlights).

One row per moment worth celebrating, detected by `services/highlights.py` from the gap
between two consecutive `player_weekly_stats` readings. The frontend reads them through
`GET /api/highlights` to play the in-app celebration; Web Push will send from the same
rows, which is why they are stored rather than riding on the SSE event itself — an event
dropped while the phone was asleep would be a touchdown nobody hears about.

The unique key is the dedupe: `ordinal` is the stat's NEW count (his 2nd rushing TD is
`rush_td` / 2), so re-reading the same stat line — the next live tick, the 30-minute full
pass, a server restart — collides and inserts nothing.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PlayerHighlight(Base):
    __tablename__ = "player_highlights"
    __table_args__ = (UniqueConstraint("sleeper_id", "season", "week", "stat_key", "ordinal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sleeper_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Ours, for the name and headshot. When he is on user teams in two leagues this is
    # whichever row the detector met first — both describe the same man.
    player_id: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    # "touchdown" | "big_play"
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # The Sleeper stat that moved: `rush_td`, `rec_40p`, ...
    stat_key: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # Yards on the play when the feed says (`rec_td_lng` after a receiving TD), else null.
    yards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # His whole line at the moment it fired ("6 rec · 112 yds · 2 TD") — frozen here so a
    # later replay shows the game as it stood, not as it ended.
    stat_line: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
