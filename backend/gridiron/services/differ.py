"""Snapshot diffing -> SSE `data.changed` scopes (task 8.4).

Fingerprints are cheap hashes over the *current week's* read-model rows. The
`fantasy_service` seam comment ("Phase 8: SSE events must never fire for past weeks") is
honored by construction here: `fantasy_fingerprints` only ever looks at the `week` its
caller passes in, and every caller (`fantasy_service.refresh_fantasy`) passes
`current_week(session)` — never an arbitrary/past week.

Module-level `_LAST_FINGERPRINTS` remembers the previous run's fingerprint per scope —
single-process, single-user app (design.md D1), same pattern as
`fantasy_service._LAST_ERRORS`. `reset_state()` clears it for tests.
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import (
    DraftPick,
    DraftSession,
    League,
    LiveNflGame,
    Matchup,
    RosterSlot,
    SeasonWeek,
    Team,
)
from backend.gridiron.schemas.events import DataChangedEvent
from backend.gridiron.services import events

_LAST_FINGERPRINTS: dict[str, str] = {}


def reset_state() -> None:
    _LAST_FINGERPRINTS.clear()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def diff_and_publish(fingerprints: dict[str, str]) -> list[str]:
    """Compare `fingerprints` (scope -> hash) against the previous call's, publish
    `data.changed` for whatever changed (or is new), and return the changed scopes.

    A scope missing from `fingerprints` this round is left alone (its last-known
    fingerprint stays, unpublished) — callers only pass the scopes they actually
    recomputed this tick.
    """
    changed = sorted(
        scope
        for scope, fingerprint in fingerprints.items()
        if _LAST_FINGERPRINTS.get(scope) != fingerprint
    )
    _LAST_FINGERPRINTS.update(fingerprints)
    if changed:
        events.publish(
            DataChangedEvent(scopes=changed, as_of=datetime.now(UTC).replace(tzinfo=None))
        )
    return changed


async def fantasy_fingerprints(session: AsyncSession, week: int) -> dict[str, str]:
    """Per-scope fingerprints for `week` across every user team in an enabled league:
    `"teams"` (the aggregate list), `"team:{id}"` (that team's roster points),
    `"h2h:{id}"` (its matchup score), `"season:{id}"` (its season-week row).

    Only ever called with `week = current_week(session)` — see the module docstring.
    """
    team_rows = (
        (
            await session.execute(
                select(Team)
                .join(League, Team.league_id == League.id)
                .where(Team.is_user_team.is_(True), League.is_enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )
    if not team_rows:
        return {}

    team_ids = [t.id for t in team_rows]

    matchup_rows = (
        (
            await session.execute(
                select(Matchup).where(
                    Matchup.week == week,
                    (Matchup.home_team_id.in_(team_ids)) | (Matchup.away_team_id.in_(team_ids)),
                )
            )
        )
        .scalars()
        .all()
    )
    matchup_by_team: dict[str, Matchup] = {}
    for matchup in matchup_rows:
        if matchup.home_team_id in team_ids:
            matchup_by_team[matchup.home_team_id] = matchup
        if matchup.away_team_id in team_ids:
            matchup_by_team[matchup.away_team_id] = matchup

    roster_rows = (
        await session.execute(
            select(RosterSlot.team_id, RosterSlot.player_id, RosterSlot.actual_points).where(
                RosterSlot.team_id.in_(team_ids), RosterSlot.week == week
            )
        )
    ).all()
    roster_by_team: dict[str, list[tuple[str, float]]] = {}
    for team_id, player_id, actual_points in roster_rows:
        roster_by_team.setdefault(team_id, []).append((player_id, actual_points))

    season_rows = (
        await session.execute(
            select(SeasonWeek.team_id, SeasonWeek.score, SeasonWeek.opp_score).where(
                SeasonWeek.team_id.in_(team_ids), SeasonWeek.week == week
            )
        )
    ).all()
    season_by_team = {team_id: (score, opp_score) for team_id, score, opp_score in season_rows}

    fingerprints: dict[str, str] = {}
    teams_payload = []
    for team in sorted(team_rows, key=lambda t: t.id):
        matchup = matchup_by_team.get(team.id)
        if matchup is not None:
            current, opp = (
                (matchup.home_score, matchup.away_score)
                if matchup.home_team_id == team.id
                else (matchup.away_score, matchup.home_score)
            )
        else:
            current, opp = 0.0, 0.0
        teams_payload.append((team.id, current, opp))

        fingerprints[f"team:{team.id}"] = _fingerprint(sorted(roster_by_team.get(team.id, [])))

        if matchup is not None:
            fingerprints[f"h2h:{team.id}"] = _fingerprint(
                (matchup.id, matchup.home_score, matchup.away_score, matchup.is_complete)
            )

        season = season_by_team.get(team.id)
        if season is not None:
            fingerprints[f"season:{team.id}"] = _fingerprint(season)

    fingerprints["teams"] = _fingerprint(teams_payload)
    return fingerprints


async def draft_fingerprints(session: AsyncSession) -> dict[str, str]:
    """Single `"draft"` scope fingerprinting `(max(overall_pick), count(picks),
    current_overall_pick)`, plus the `draft_sessions` row's `status` ONLY when a row
    exists. Manual-only draft-night operation may have zero `draft_sessions` rows (that
    row is created lazily by `draft_state._get_or_create_session_row` on the first
    pick/current-pick write, per D13) -- the session term must be optional rather than
    raising, so this never blocks the manual-only path.

    Called from `draft_state.record_pick`/`undo_last_pick` (via `api/draft.py`) after
    every commit, not just from a poller tick, so a manual pick fires the SSE event too.
    """
    max_pick = (await session.execute(select(func.max(DraftPick.overall_pick)))).scalar()
    pick_count = (await session.execute(select(func.count(DraftPick.id)))).scalar() or 0

    session_row = (
        (await session.execute(select(DraftSession).order_by(DraftSession.id).limit(1)))
        .scalars()
        .first()
    )
    current_pick = session_row.current_overall_pick if session_row is not None else None
    status = session_row.status if session_row is not None else None

    payload = (max_pick, pick_count, current_pick, status)
    return {"draft": _fingerprint(payload)}


async def live_nfl_games_fingerprints(session: AsyncSession) -> dict[str, str]:
    """Single `"live_nfl_games"` scope fingerprinting every row's score/state/clock."""
    rows = (await session.execute(select(LiveNflGame))).scalars().all()
    payload = sorted(
        (row.nfl_game_id, row.home_score, row.away_score, row.state, row.clock, row.period)
        for row in rows
    )
    return {"live_nfl_games": _fingerprint(payload)}
