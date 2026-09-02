"""ESPN core injury-report client/mapper/upsert (add-player-health)."""

from datetime import datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, PlayerInjury
from backend.gridiron.platforms import espn_injuries

FETCHED_AT = datetime(2026, 9, 2, 12, 0, 0)

# Trimmed from a live response for athlete 4428209 (Ricky Pearsall), 2026-09-02.
REPORT_PAYLOAD = {
    "count": 1,
    "items": [
        {
            "id": "633398",
            "status": "Injured Reserve",
            "date": "2026-08-13T15:11Z",
            "shortComment": "Pearsall underwent season-ending surgery.",
            "longComment": "The procedure typically carries a 6-to-12 month recovery.",
            "details": {
                "type": "Knee - PCL",
                "location": "Leg",
                "detail": "Surgery",
                "side": "Right",
                "returnDate": "2027-02-15",
            },
        }
    ],
}

HEALTHY_PAYLOAD = {"count": 0, "pageCount": 0, "items": []}


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "injuries.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class FakeClient:
    """Records every (season, athlete_id) asked for, so the tests can assert on which
    players were swept as well as on what was stored."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses
        self.calls: list[tuple[int, str]] = []

    async def get_injuries(self, season: int, athlete_id: str) -> dict:
        self.calls.append((season, athlete_id))
        payload = self._responses.get(athlete_id)
        if payload is None:
            raise httpx.HTTPError(f"boom {athlete_id}")
        return payload

    async def aclose(self) -> None:  # pragma: no cover - never owned by the code under test
        pass


async def seed(db, players: list[tuple[str, str | None]], season: int = 2026) -> None:
    async with db() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=season,
                team_count=10,
                scoring_type="ppr",
                current_week=1,
            )
        )
        for player_id, status in players:
            session.add(
                Player(
                    id=player_id,
                    platform=player_id.split(":")[0],
                    platform_id=player_id.split(":")[1],
                    name=player_id,
                    position="WR",
                    nfl_team="SF",
                    injury_status=status,
                )
            )
        await session.commit()


# --------------------------------------------------------------------------------------
# id classification
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "player_id,expected",
    [
        ("espn:p-4428209", "4428209"),
        # D/ST ids are synthetic and negative — there is no such athlete.
        ("espn:p--16007", None),
        # No ESPN athlete id exists for a Yahoo-sourced player.
        ("yahoo:p-30123", None),
    ],
)
def test_espn_athlete_id(player_id, expected):
    assert espn_injuries.espn_athlete_id(player_id) == expected
    assert espn_injuries.detail_supported(player_id) is (expected is not None)


# --------------------------------------------------------------------------------------
# mapper
# --------------------------------------------------------------------------------------


def test_map_injury_reads_every_detail_field():
    row = espn_injuries.map_injury("espn:p-4428209", REPORT_PAYLOAD, fetched_at=FETCHED_AT)
    assert row is not None
    assert row.report_id == "633398"
    assert row.status == "Injured Reserve"
    assert row.injury_type == "Knee - PCL"
    assert row.location == "Leg"
    assert row.detail == "Surgery"
    assert row.side == "Right"
    assert row.return_date == "2027-02-15"
    assert row.short_comment.startswith("Pearsall")
    assert row.long_comment.startswith("The procedure")
    # "2026-08-13T15:11Z" -> naive UTC, matching the rest of the codebase.
    assert row.reported_at == datetime(2026, 8, 13, 15, 11)
    assert row.fetched_at == FETCHED_AT


def test_map_injury_returns_none_for_the_healthy_response():
    """`count: 0` is the ordinary answer for a healthy player, not an error."""
    assert espn_injuries.map_injury("espn:p-1", HEALTHY_PAYLOAD, fetched_at=FETCHED_AT) is None


def test_map_injury_survives_a_report_with_no_details():
    """ESPN files practice-report entries carrying only a status and a date."""
    payload = {"count": 1, "items": [{"id": "1", "status": "Questionable", "date": None}]}
    row = espn_injuries.map_injury("espn:p-1", payload, fetched_at=FETCHED_AT)
    assert row is not None
    assert row.status == "Questionable"
    assert row.injury_type is None
    assert row.reported_at is None


# --------------------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------------------


async def test_fetch_and_upsert_sweeps_only_unhealthy_espn_players(db):
    await seed(
        db,
        [
            ("espn:p-4428209", "IR"),
            ("espn:p-100", "ACTIVE"),  # healthy — not worth a request
            ("espn:p-101", None),  # unknown — nothing to look up
            ("espn:p--16007", "O"),  # D/ST — no athlete endpoint
            ("yahoo:p-30123", "Q"),  # no ESPN athlete id
        ],
    )
    client = FakeClient({"4428209": REPORT_PAYLOAD})

    async with db() as session:
        assert await espn_injuries.fetch_and_upsert(session, client) is None

    assert client.calls == [(2026, "4428209")]
    async with db() as session:
        rows = (await session.execute(select(PlayerInjury))).scalars().all()
    assert [r.player_id for r in rows] == ["espn:p-4428209"]
    assert rows[0].injury_type == "Knee - PCL"


async def test_fetch_and_upsert_clears_a_resolved_report(db):
    """A player ESPN no longer has a report for must not keep showing a stale injury."""
    await seed(db, [("espn:p-4428209", "Q")])
    async with db() as session:
        session.add(
            PlayerInjury(
                player_id="espn:p-4428209",
                status="Questionable",
                injury_type="Hamstring",
                fetched_at=FETCHED_AT,
            )
        )
        await session.commit()

    async with db() as session:
        await espn_injuries.fetch_and_upsert(session, FakeClient({"4428209": HEALTHY_PAYLOAD}))

    async with db() as session:
        assert (await session.execute(select(PlayerInjury))).scalars().all() == []


async def test_one_failing_athlete_does_not_abort_the_sweep(db):
    await seed(db, [("espn:p-1", "Q"), ("espn:p-4428209", "IR")])
    # p-1 is absent from the fake's responses, so its fetch raises.
    client = FakeClient({"4428209": REPORT_PAYLOAD})

    async with db() as session:
        error = await espn_injuries.fetch_and_upsert(session, client)

    assert error is not None and "espn:p-1" in error
    async with db() as session:
        rows = (await session.execute(select(PlayerInjury))).scalars().all()
    assert [r.player_id for r in rows] == ["espn:p-4428209"]


async def test_season_comes_from_the_persisted_leagues(db):
    """The season is part of the URL path and is NOT interchangeable: the same athlete
    returns `count: 0` under the wrong year."""
    await seed(db, [("espn:p-4428209", "IR")], season=2031)
    client = FakeClient({"4428209": REPORT_PAYLOAD})
    async with db() as session:
        await espn_injuries.fetch_and_upsert(session, client)
    assert client.calls == [(2031, "4428209")]
