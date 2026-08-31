#!/usr/bin/env python
"""Spike: what does ESPN give us for fantasy-team logos, and who can fetch them?

READ-ONLY BY CONSTRUCTION — every request is a GET. Nothing is written upstream.

Run:  PYTHONPATH=. uv run python scripts/probe-espn-team-logos.py

This is the reproducer for the three findings `add-league-standings/design.md` rests
on. Re-run it when logos stop rendering; ESPN's fantasy API is undocumented and these
hosts and formats can change without notice.

  P1  Does every team carry a logo? (design assumes yes, from `mTeam`)
  P2  What formats? Two exist: `VECTOR` (ESPN's stock SVG set) and `CUSTOM_UPLOAD`
      (an extensionless URL). The format cannot be read off the URL, which is why
      the content type is stored per row rather than inferred.
  P3  Who can fetch them? THE load-bearing question. If uploaded logos require
      session cookies, the browser cannot render them directly and the backend must
      proxy — that is the entire reason a local logo cache exists.
"""

import asyncio
import json
from collections import Counter
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from backend.gridiron.config import get_settings
from backend.gridiron.db import async_session_factory
from backend.gridiron.models import Connection, HttpCache
from backend.gridiron.services import credentials


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


async def cached_league_payloads() -> list[dict]:
    async with async_session_factory() as session:
        rows = (
            (await session.execute(select(HttpCache).where(HttpCache.endpoint == "league")))
            .scalars()
            .all()
        )
    return [json.loads(r.raw_json) for r in rows if r.raw_json]


async def main() -> None:
    swid, espn_s2 = await load_cookies()
    payloads = await cached_league_payloads()
    if not payloads:
        raise SystemExit("no cached league payloads — run a sync_discovery first")

    print(f"### P1 — logo presence across {len(payloads)} cached leagues")
    by_type: dict[str, str] = {}
    total = with_logo = 0
    for raw in payloads:
        teams = raw.get("teams", [])
        total += len(teams)
        for t in teams:
            if t.get("logo"):
                with_logo += 1
                by_type.setdefault(t.get("logoType", "?"), t["logo"])
    print(f"    {with_logo}/{total} teams carry a logo")

    print("\n### P2 — formats, and why the URL cannot be trusted for one")
    kinds = Counter()
    for raw in payloads:
        for t in raw.get("teams", []):
            url = t.get("logo") or ""
            kinds[(t.get("logoType"), urlparse(url).hostname)] += 1
    for (logo_type, host), n in kinds.most_common():
        print(f"    {str(logo_type):16} {str(host):36} x{n}")

    print("\n### P3 — who can fetch them (the decision this probe exists for)")
    for authed in (False, True):
        headers = {"Cookie": f"SWID={swid}; espn_s2={espn_s2}"} if authed else {}
        label = "with cookies" if authed else "no cookies  "
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for logo_type, url in sorted(by_type.items()):
                try:
                    r = await client.get(url, headers=headers)
                    ct = (r.headers.get("content-type") or "").split(";")[0]
                    print(
                        f"    {label}  {logo_type:16} {r.status_code}  "
                        f"{ct:20} {len(r.content):>8,}B"
                    )
                except Exception as exc:  # noqa: BLE001 — a probe reports, it does not raise
                    print(f"    {label}  {logo_type:16} ERROR {exc!r}")

    print(
        "\nA 401 in the 'no cookies' row for an uploaded logo means a browser cannot\n"
        "render it directly, and the backend proxy is required rather than optional."
    )


if __name__ == "__main__":
    asyncio.run(main())
