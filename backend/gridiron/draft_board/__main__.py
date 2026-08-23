"""CLI entry point: `python -m backend.gridiron.draft_board import`."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.draft_board import run_import
from backend.gridiron.models import Base


async def _main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] != "import":
        print("usage: python -m backend.gridiron.draft_board import", file=sys.stderr)
        return 2

    engine = make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            report = await run_import(session)
    finally:
        await engine.dispose()

    print(f"Board players seen this import: {report.players_seen}")
    print(f"Board players total in DB:      {report.board_players_total}")
    print(f"Tiers seen this import:         {report.tiers_seen}")
    print(f"Heuristics seen this import:    {report.heuristics_seen}")

    if report.flag_omission_defects:
        print()
        print(
            "SOURCE DATA DEFECT: the following players have risk_score >= 4 but an EMPTY "
            "`flags` array in players.json (the export appears to drop FADE for at least "
            "some high-risk players). This can only be fixed by re-exporting the board "
            "data upstream:"
        )
        for name in report.flag_omission_defects:
            print(f"  - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
