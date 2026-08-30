#!/usr/bin/env python
"""Spike: does ESPN's *write* API accept our stored credentials?

READ-ONLY BY CONSTRUCTION. This script never changes a lineup. It answers one
question — "would a lineup write be authorized?" — by exercising the write host's
auth and routing without submitting an applicable transaction.

Run:  uv run python scripts/probe-espn-writes.py [--league-id N]

Background. ESPN splits its private fantasy API across two hosts:

    lm-api-reads.fantasy.espn.com    <- what this app uses today (config.espn_base_url)
    lm-api-writes.fantasy.espn.com   <- lineup changes, adds/drops, waiver claims

Both take the same `SWID` + `espn_s2` cookie auth, so if the reads host trusts our
cookies the writes host generally will too. "Generally" is the part worth testing:
ESPN has historically applied stricter checks on the write host, and the failure is
silent enough (a 200 with an error body) that assuming is not good enough.

A real lineup change would POST to

    /apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league}/transactions/

with `type: "ROSTER"`, `executionType: "EXECUTE"`, and an `items` list pairing two
players' `fromLineupSlotId`/`toLineupSlotId` — the same lineupSlotId vocabulary
already tabulated in backend/gridiron/platforms/espn/slot_table.py.

The probe below sends that shape with an EMPTY `items` list. That is the whole
safety argument: a ROSTER transaction with no items has nothing to apply, so even
if ESPN executed it in full it could not move a player. What the response code
tells us:

    401 / 403        -> cookies are not accepted for writes (a real blocker)
    400 / 422 / 200  -> cookies WERE accepted; the payload was evaluated
                        (i.e. auth is not the obstacle to building this feature)

Two things this probe deliberately does NOT establish: that the exact field names
above are current (ESPN changes them without notice — confirm against the browser's
Network tab during a real lineup change), and that a populated transaction would
succeed. It only rules auth in or out.
"""

import argparse
import asyncio
import json

import httpx
from sqlalchemy import select

from backend.gridiron.config import get_settings
from backend.gridiron.db import async_session_factory
from backend.gridiron.models import Connection, League, Team
from backend.gridiron.services import credentials

WRITES_BASE = "https://lm-api-writes.fantasy.espn.com"
SEASON_SEGMENT = 0


async def load_cookies() -> tuple[str, str]:
    settings = get_settings()
    async with async_session_factory() as session:
        conn = await session.get(Connection, "espn")
        if conn is None or not conn.swid_enc or not conn.espn_s2_enc:
            raise SystemExit("no stored ESPN credentials — connect ESPN in Settings first")
        return (
            credentials.decrypt(settings.gridiron_secret_key, conn.swid_enc),
            credentials.decrypt(settings.gridiron_secret_key, conn.espn_s2_enc),
        )


async def user_team_id(league_internal_id: str) -> int:
    """ESPN's numeric teamId for our team in this league, off the local `teams` rows."""
    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    select(Team).where(
                        Team.league_id == league_internal_id, Team.is_user_team.is_(True)
                    )
                )
            )
            .scalars()
            .first()
        )
    if row is None:
        raise SystemExit(f"no user team recorded for {league_internal_id}")
    # Team ids are "espn:l-{league}-t-{team}"; the numeric id ESPN wants is the tail.
    return int(row.platform_id.rsplit("-t-", 1)[1])


async def pick_league(explicit: int | None) -> tuple[int, int, str]:
    if explicit is not None:
        async with async_session_factory() as session:
            row = await session.get(League, f"espn:{explicit}")
            if row is None:
                raise SystemExit(f"league espn:{explicit} not in the local DB")
            return explicit, row.season, row.name
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(League).where(League.platform == "espn", League.is_enabled.is_(True))
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        raise SystemExit("no enabled ESPN leagues in the local DB")
    row = rows[0]
    return int(row.platform_id), row.season, row.name


def show(label: str, response: httpx.Response) -> None:
    body = response.text.strip()
    if len(body) > 300:
        body = body[:300] + "…"
    print(f"  {label}")
    print(f"    status : {response.status_code}")
    print(f"    body   : {body or '(empty)'}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, default=None)
    args = parser.parse_args()

    swid, espn_s2 = await load_cookies()
    league_id, season, league_name = await pick_league(args.league_id)
    team_id = await user_team_id(f"espn:{league_id}")
    print(f"league : {league_name} (espn:{league_id}, season {season})")
    print(f"team   : {team_id}")
    print(f"host   : {WRITES_BASE}\n")

    cookies = {"Cookie": f"SWID={swid}; espn_s2={espn_s2}"}
    league_path = (
        f"/apis/v3/games/ffl/seasons/{season}/segments/{SEASON_SEGMENT}/leagues/{league_id}"
    )

    async with httpx.AsyncClient(base_url=WRITES_BASE, timeout=20, headers=cookies) as http:
        # --- Step 1: confirm the host is write-only ---------------------------------
        # This started as "GET the league to check auth", which was a bad assumption:
        # the write host serves no GETs at all and answers 405 before it ever looks at
        # a cookie. Kept, reframed, because the 405 is itself worth recording — it
        # documents that reads and writes genuinely cannot share one client/base_url.
        print("step 1 — GET on the WRITE host (expected 405: this host takes writes only)")
        try:
            show("GET " + league_path, await http.get(league_path, params={"view": "mTeam"}))
        except httpx.HTTPError as exc:
            print(f"    transport error: {exc!r}")

        # --- Step 2: POST a ROSTER transaction with NO items ------------------------
        # Empty `items` is the safety property: nothing to apply, so nothing can move.
        print("\nstep 2 — POST an EMPTY ROSTER transaction (no items => cannot move a player)")
        payload = {
            "isLeagueManager": False,
            "teamId": team_id,
            "type": "ROSTER",
            "executionType": "EXECUTE",
            "memberId": swid,
            "scoringPeriodId": 1,
            "items": [],
        }
        print("    payload:", json.dumps(payload | {"memberId": "{SWID}"}))
        try:
            show(
                f"POST {league_path}/transactions/",
                await http.post(f"{league_path}/transactions/", json=payload),
            )
        except httpx.HTTPError as exc:
            print(f"    transport error: {exc!r}")

    print(
        "\ninterpretation:"
        "\n  401 / 403                 -> writes are NOT authorized with these cookies."
        "\n  409 TRAN_ITEMS_MISSING    -> fully authorized. ESPN resolved the SWID to a"
        "\n                               member, resolved teamId to our team, confirmed"
        "\n                               we own it, accepted the type/period, and"
        "\n                               rejected ONLY the empty items array."
        "\n  409 TEAM_NOT_FOUND        -> teamId wrong for this league."
        "\n  409 TRAN_TYPE_NOT_ALLOWED -> league state forbids it (e.g. pre-draft)."
    )


if __name__ == "__main__":
    asyncio.run(main())
