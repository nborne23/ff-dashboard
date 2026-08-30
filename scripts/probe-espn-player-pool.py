#!/usr/bin/env python
"""Spike: what does ESPN's `kona_player_info` view actually give us?

READ-ONLY BY CONSTRUCTION — every request here is a GET against the same reads host
(`config.espn_base_url`) the app already uses. Nothing is written, locally or upstream.

Run:  uv run python scripts/probe-espn-player-pool.py

Context. A free-agent/waiver view and any rest-of-season ranking both need two things
this app does not store today: the pool of players NOT on one of our rosters, and a
season-level projection. The working assumption is that `view=kona_player_info` carries
both in one call, filtered by an `x-fantasy-filter` JSON header. That assumption is
load-bearing for the schema, so it gets probed before anything is designed.

Four questions, and why each one changes the design:

  Q1  Which (scoringPeriodId, statSourceId, statSplitTypeId) tuples come back per
      player? `mapper._player_points` filters on `scoringPeriodId == week`, which by
      construction cannot see a season-level row. Whatever accessor the pool needs is
      a NEW one, and this says what it must match on.

  Q2  Is `appliedTotal` league-scoped? THE discriminating question for the schema.
      `appliedTotal` is a scored value, so if two leagues with different scoring types
      report different totals for the same playerId, projections cannot hang off the
      `players` table and need a per-(league, player) row. We have both kinds locally
      (`GAS Lab 2025` is ppr, `THE LEAGUE` is half_ppr), so this is testable.

  Q3  What does the `x-fantasy-filter` header have to be, and how big is the response?
      The filter is not plumbing garnish — `filterStatus` IS how the pool is selected.
      Size matters because `_cached_league_fetch` persists raw response text per
      design.md D7, and this payload is nothing like a roster's.

  Q4  Does FA/waiver status arrive in the same payload as the projection, or does
      pulling both take two calls?
"""

import asyncio
import json
from collections import Counter

import httpx
from sqlalchemy import select

from backend.gridiron.config import get_settings
from backend.gridiron.db import async_session_factory
from backend.gridiron.models import Connection, League
from backend.gridiron.services import credentials

SEASON_SEGMENT = 0
POOL_SAMPLE_LIMIT = 50


def league_path(league_id: int, year: int) -> str:
    return f"/apis/v3/games/ffl/seasons/{year}/segments/{SEASON_SEGMENT}/leagues/{league_id}"


def pool_filter(limit: int = POOL_SAMPLE_LIMIT) -> str:
    """`filterStatus` is the query: FREEAGENT/WAIVERS is precisely the pool we lack."""
    return json.dumps(
        {
            "players": {
                "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                "limit": limit,
                "offset": 0,
                "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
            }
        }
    )


def single_player_filter(player_id: int) -> str:
    return json.dumps({"players": {"filterIds": {"value": [player_id]}, "limit": 5}})


def raw_stats(player: dict) -> list[dict]:
    """Full stat dicts minus the bulky per-stat maps — for telling apart the two
    (scoringPeriodId=0, statSourceId=1) season-projection rows the first pass found."""
    out = []
    for s in player.get("stats", []):
        out.append({k: v for k, v in s.items() if k not in ("stats", "appliedStats")})
    return out


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


async def leagues_by_scoring() -> list[tuple[int, str, int, str]]:
    """(numeric espn league id, name, season, scoring_type) for every stored league."""
    async with async_session_factory() as session:
        rows = (await session.execute(select(League))).scalars().all()
    out = []
    for row in rows:
        platform, _, raw_id = row.id.partition(":")
        if platform != "espn":
            continue
        out.append((int(raw_id), row.name, row.season, row.scoring_type))
    return out


def stat_tuples(player: dict) -> list[tuple]:
    """(scoringPeriodId, statSourceId, statSplitTypeId, appliedTotal) — the shape question."""
    return [
        (
            s.get("scoringPeriodId"),
            s.get("statSourceId"),
            s.get("statSplitTypeId"),
            round(s.get("appliedTotal", 0.0), 2),
        )
        for s in player.get("stats", [])
    ]


def entry_player(entry: dict) -> dict:
    return entry.get("playerPoolEntry", {}).get("player", entry.get("player", {}))


async def probe_pool(client: httpx.AsyncClient, league_id: int, year: int, label: str) -> dict:
    resp = await client.get(
        league_path(league_id, year),
        params={"view": "kona_player_info"},
        headers={"x-fantasy-filter": pool_filter()},
    )
    print(f"\n### Q3/Q4 — pool fetch [{label}] league={league_id}")
    print(f"    status      : {resp.status_code}")
    print(f"    bytes       : {len(resp.content):,} for limit={POOL_SAMPLE_LIMIT}")
    if resp.status_code != 200:
        print(f"    body        : {resp.text[:400]}")
        return {}

    body = resp.json()
    entries = body.get("players", [])
    print(f"    players     : {len(entries)}")
    if not entries:
        print("    (empty — filter may be wrong; top-level keys: "
              f"{sorted(body.keys())})")
        return body

    first = entries[0]
    player = entry_player(first)
    print(f"    entry keys  : {sorted(first.keys())}")
    print(f"    player keys : {sorted(player.keys())}")
    print(f"    Q4 status   : status={first.get('status')!r} "
          f"onTeamId={first.get('onTeamId')!r} "
          f"pctOwned={player.get('ownership', {}).get('percentOwned')!r}")
    print(f"    sample      : {player.get('fullName')!r}")
    print("    Q1 stats (scoringPeriodId, statSourceId, statSplitTypeId, appliedTotal):")
    for t in stat_tuples(player):
        print(f"        {t}")

    spread = Counter(
        (s.get("scoringPeriodId"), s.get("statSourceId"), s.get("statSplitTypeId"))
        for e in entries
        for s in entry_player(e).get("stats", [])
    )
    print("    Q1 tuple frequency across all sampled players:")
    for tup, n in spread.most_common(12):
        print(f"        {tup}  x{n}")
    return body


async def probe_league_scoping(
    client: httpx.AsyncClient, leagues: list[tuple[int, str, int, str]]
) -> None:
    """Q2 — same playerId, different league scoring types. Do the numbers move?

    `filterIds` came back 400 on the first pass, so this pulls the SAME ranked pool
    filter from each league and intersects on player id instead. Same question, and it
    reuses a filter already proven to work.
    """
    print("\n### Q2 — league-scoping of appliedTotal (season projections)")
    per_league: dict[str, dict[int, tuple[str, list[tuple]]]] = {}
    for league_id, league_name, year, scoring in leagues:
        resp = await client.get(
            league_path(league_id, year),
            params={"view": "kona_player_info"},
            # 50 was too narrow: one of these leagues is undrafted, so its top-50 FAs
            # are the league-winners and the other's are waiver dregs — zero overlap.
            # 400 reaches deep enough that both pools contain the same fringe players.
            headers={"x-fantasy-filter": pool_filter(400)},
        )
        if resp.status_code != 200:
            print(f"    [{scoring:9}] {league_name}: HTTP {resp.status_code} {resp.text[:200]}")
            continue
        by_id = {}
        for e in resp.json().get("players", []):
            p = entry_player(e)
            season_proj = [
                t for t in stat_tuples(p) if t[0] == 0 and t[1] == 1
            ]  # season-scope projections only
            by_id[p.get("id")] = (p.get("fullName", "?"), season_proj)
        per_league[f"{scoring}:{league_name}"] = by_id
        print(f"    [{scoring:9}] {league_name}: {len(by_id)} players")

    if len(per_league) < 2:
        print("    not enough leagues responded to compare")
        return

    keys = list(per_league)
    shared = set(per_league[keys[0]]) & set(per_league[keys[1]])
    print(f"\n    {len(shared)} players present in both {keys[0]} and {keys[1]}")
    for pid in list(shared)[:6]:
        name = per_league[keys[0]][pid][0]
        a = per_league[keys[0]][pid][1]
        b = per_league[keys[1]][pid][1]
        verdict = "SAME" if a == b else "DIFFERS"
        print(f"      {name:24} {verdict}")
        print(f"          {keys[0]:32} {a}")
        print(f"          {keys[1]:32} {b}")


async def probe_limits_and_status(
    client: httpx.AsyncClient, leagues: list[tuple[int, str, int, str]]
) -> None:
    """Q6 — two questions the first pass left open, and they interact.

    (a) Asking for limit=1500 returned 1030. Is 1030 the real player count, or a
        server-side ceiling? If it caps, the fetch needs `offset` pagination.
    (b) The FREEAGENT/WAIVERS filter cannot return rostered players, so nothing would
        carry a SEASON projection for a player already on a roster — and
        `roster_slots.proj_points` is a WEEKLY number (21.57 vs 364.86 for Gibbs).
        Comparing a candidate against a starter needs both on the same scale, so this
        checks what adding ONTEAM costs.

    Also reports a drafted vs undrafted league separately: an undrafted league's "free
    agent pool" is the entire player universe, so its size is not representative.
    """
    print("\n### Q6 — limit ceiling and ONTEAM cost")
    statuses = {
        "FA+WAIVERS": ["FREEAGENT", "WAIVERS"],
        "FA+WAIVERS+ONTEAM": ["FREEAGENT", "WAIVERS", "ONTEAM"],
    }
    for league_id, league_name, year, scoring in leagues:
        for label, value in statuses.items():
            filt = json.dumps(
                {
                    "players": {
                        "filterStatus": {"value": value},
                        "limit": 3000,
                        "offset": 0,
                        "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
                    }
                }
            )
            resp = await client.get(
                league_path(league_id, year),
                params={"view": "kona_player_info"},
                headers={"x-fantasy-filter": filt},
            )
            if resp.status_code != 200:
                print(f"    {league_name:32} {label:20} HTTP {resp.status_code}")
                continue
            entries = resp.json().get("players", [])
            on_team = sum(1 for e in entries if e.get("status") == "ONTEAM")
            print(
                f"    {league_name:32} {label:20} {len(entries):>5} players "
                f"({on_team:>4} ONTEAM)  {len(resp.content):>10,} bytes"
            )


async def probe_eligibility_and_positions(
    client: httpx.AsyncClient, league_id: int, year: int
) -> None:
    """Q7 — two vocabulary questions the schema depends on.

    (a) `eligibleSlots` is a list of raw lineupSlotId ints. They map to UNNUMBERED
        names (RB, WR, FLEX) via LINEUP_SLOT_MAP — there is no basis for RB1 vs RB2
        off a roster, since the internal Slot numbering comes from per-roster
        counters. So the eligibility type cannot be the internal `Slot`. This reports
        which ids actually appear and whether LINEUP_SLOT_MAP covers them.
    (b) `Player.position` is a 6-value Literal. A 1030-player league-wide catalog
        contains more than six positions, so this counts how many entries would be
        skipped by design D6 — task 6.2 expects "a handful, not hundreds."
    """
    from backend.gridiron.platforms.espn.slot_table import LINEUP_SLOT_MAP

    resp = await client.get(
        league_path(league_id, year),
        params={"view": "kona_player_info"},
        headers={"x-fantasy-filter": pool_filter(1500)},
    )
    if resp.status_code != 200:
        print(f"\n### Q7 — HTTP {resp.status_code}")
        return
    entries = resp.json().get("players", [])

    slot_ids = Counter()
    for e in entries:
        for sid in entry_player(e).get("eligibleSlots", []):
            slot_ids[sid] += 1
    known = {sid: LINEUP_SLOT_MAP.get(sid) for sid in sorted(slot_ids)}
    unknown = [sid for sid, name in known.items() if name is None]

    print(f"\n### Q7a — eligibleSlots vocabulary across {len(entries)} players")
    print(f"    distinct lineupSlotIds: {sorted(slot_ids)}")
    print(f"    mapped: {[(sid, n) for sid, n in known.items() if n]}")
    print(f"    UNMAPPED (espn_slot_name would raise): {unknown or 'none'}")

    pos_ids = Counter(entry_player(e).get("defaultPositionId") for e in entries)
    print(f"\n### Q7b — defaultPositionId distribution ({len(entries)} players)")
    for pid, n in sorted(pos_ids.items(), key=lambda kv: -kv[1]):
        print(f"    id={pid:<4} x{n}")


async def probe_pool_size(client: httpx.AsyncClient, league_id: int, year: int) -> None:
    """Q5 — what does a FULL pool pull actually cost? `_cached_league_fetch` persists
    raw response text per design.md D7; this is the number that decides whether the
    pool gets an exception to that."""
    resp = await client.get(
        league_path(league_id, year),
        params={"view": "kona_player_info"},
        headers={"x-fantasy-filter": pool_filter(1500)},
    )
    n = len(resp.json().get("players", [])) if resp.status_code == 200 else 0
    print(f"\n### Q5 — full-pool cost (limit=1500): HTTP {resp.status_code}, "
          f"{n} players, {len(resp.content):,} bytes")
    if n:
        print(f"    ~{len(resp.content) / n:,.0f} bytes/player  ->  "
              f"~{len(resp.content) * 5 / 1e6:,.1f} MB per full refresh across 5 leagues")


async def main() -> None:
    settings = get_settings()
    swid, espn_s2 = await load_cookies()
    leagues = await leagues_by_scoring()
    if not leagues:
        raise SystemExit("no ESPN leagues stored — run a sync first")

    print("stored ESPN leagues:")
    for league_id, name, year, scoring in leagues:
        print(f"    {league_id:>12}  {scoring:9}  {name} ({year})")

    async with httpx.AsyncClient(
        base_url=settings.espn_base_url,
        timeout=30,
        headers={"Cookie": f"SWID={swid}; espn_s2={espn_s2}"},
    ) as client:
        first_league_id, first_name, year, _ = leagues[0]
        body = await probe_pool(client, first_league_id, year, first_name)

        # Disambiguate the two (scoringPeriodId=0, statSourceId=1) season rows.
        entries = body.get("players", []) if body else []
        if entries:
            player = entry_player(entries[0])
            print(f"\n### Q1b — full stat rows for {player.get('fullName')!r}")
            for s in raw_stats(player):
                print(f"    {s}")

        # Q2 only discriminates across DIFFERENT scoring types — pick one of each.
        by_scoring: dict[str, tuple[int, str, int, str]] = {}
        for lg in leagues:
            by_scoring.setdefault(lg[3], lg)
        if len(by_scoring) < 2:
            print("\n### Q2 — SKIPPED: all stored leagues share one scoring type "
                  f"({sorted(by_scoring)}); cannot discriminate locally.")
        else:
            await probe_league_scoping(client, list(by_scoring.values()))

        await probe_pool_size(client, first_league_id, year)
        # One undrafted league (GAS Lab) and one drafted (THE LEAGUE) — the sizes differ
        # enough that quoting either alone would be misleading.
        await probe_limits_and_status(client, leagues[:2])
        await probe_eligibility_and_positions(client, first_league_id, year)


if __name__ == "__main__":
    asyncio.run(main())
