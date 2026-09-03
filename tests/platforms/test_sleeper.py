"""Sleeper projection ingest — the three matcher tiers, ambiguity, and scope encoding."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, PlayerProjection
from backend.gridiron.platforms import sleeper

FETCHED_AT = datetime(2026, 9, 3, 12, 0, 0)


def proj_row(sleeper_id, first, last, team, position, ppr, half=None, std=None):
    return {
        "player_id": sleeper_id,
        "company": "rotowire",
        "player": {
            "first_name": first,
            "last_name": last,
            "team": team,
            "position": position,
        },
        "stats": {
            "pts_ppr": ppr,
            "pts_half_ppr": half if half is not None else ppr - 1,
            "pts_std": std if std is not None else ppr - 2,
        },
    }


# Sleeper's dump: note Etienne has NO espn_id, which is the real-world case that makes
# tier 2 carry most of the matching.
DUMP = {
    "111": {"espn_id": 3139477, "first_name": "Patrick", "last_name": "Mahomes"},
    "222": {"espn_id": None, "first_name": "Travis", "last_name": "Etienne"},
    "333": {"espn_id": 4360248, "first_name": "Kyle", "last_name": "Pitts"},
    "SEA": {"first_name": "Seattle", "last_name": "Seahawks"},
}

PROJECTIONS = [
    proj_row("111", "Patrick", "Mahomes", "KC", "QB", 21.1),
    proj_row("222", "Travis", "Etienne", "JAX", "RB", 14.4),
    proj_row("333", "Kyle", "Pitts", "ATL", "TE", 11.0),
    proj_row("SEA", "Seattle", "Seahawks", "SEA", "DEF", 8.0),
    # Teamless (free agent / practice squad) — must never be indexed by name.
    proj_row("999", "Patrick", "Mahomes", None, "QB", 99.9),
]


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "sleeper.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class FakeClient:
    def __init__(self, dump=None, projections=None):
        self._dump = DUMP if dump is None else dump
        self._proj = PROJECTIONS if projections is None else projections
        self.calls: list[int | None] = []

    async def get_players(self, session):
        return self._dump

    async def get_projections(self, season, week):
        self.calls.append(week)
        return self._proj

    async def aclose(self):  # pragma: no cover - never owned by the code under test
        pass


async def seed(db, players, season=2026, week=1, scoring="ppr"):
    async with db() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="L",
                season=season,
                team_count=10,
                scoring_type=scoring,
                current_week=week,
            )
        )
        for pid, name, pos, team in players:
            session.add(
                Player(
                    id=pid,
                    platform=pid.split(":")[0],
                    platform_id=pid.split(":")[1],
                    name=name,
                    position=pos,
                    nfl_team=team,
                )
            )
        await session.commit()


# --------------------------------------------------------------------------------------
# Matcher tiers
# --------------------------------------------------------------------------------------


def make_player(pid, name, pos, team):
    return Player(
        id=pid,
        platform=pid.split(":")[0],
        platform_id=pid.split(":")[1],
        name=name,
        position=pos,
        nfl_team=team,
    )


def test_tier_1_matches_on_espn_id():
    index = sleeper.PlayerIndex(DUMP, PROJECTIONS)
    found = index.find(make_player("espn:p-3139477", "Patrick Mahomes", "QB", "KC"))
    assert found is not None
    assert found[1] == "espn_id"
    assert found[0]["player_id"] == "111"


def test_tier_2_rescues_a_player_with_no_espn_id():
    """The case that decides whether this feature works at all: Sleeper's `espn_id` is
    missing for many recently-drafted players, so an id-only matcher reaches under a
    third of a real roster."""
    index = sleeper.PlayerIndex(DUMP, PROJECTIONS)
    found = index.find(make_player("espn:p-4239996", "Travis Etienne Jr.", "RB", "JAX"))
    assert found is not None
    assert found[1] == "name_team"
    assert found[0]["player_id"] == "222"


def test_tier_2_normalizes_generational_suffixes_and_punctuation():
    index = sleeper.PlayerIndex({}, [proj_row("1", "Ja'Marr", "Chase", "CIN", "WR", 20.0)])
    found = index.find(make_player("espn:p-1", "JaMarr Chase", "WR", "CIN"))
    assert found is not None and found[1] == "name_team"


def test_tier_3_matches_a_defense_by_team():
    index = sleeper.PlayerIndex(DUMP, PROJECTIONS)
    found = index.find(make_player("espn:p--16026", "Seahawks D/ST", "DST", "SEA"))
    assert found is not None
    assert found[1] == "dst_team"


def test_a_free_agent_never_matches_a_teamless_projection_row():
    """Our `nfl_team="FA"` and Sleeper's `team: null` are both "no team" — letting them
    meet would match on name alone and attach a stranger's projection."""
    index = sleeper.PlayerIndex({}, PROJECTIONS)
    assert index.find(make_player("espn:p-1", "Patrick Mahomes", "QB", "FA")) is None


def test_ambiguous_name_and_team_is_dropped_not_guessed():
    """Two players sharing a normalized name on one team: showing nothing beats showing
    the wrong player's number, which would be invisible once rendered."""
    rows = [
        proj_row("1", "Mike", "Williams", "NYJ", "WR", 12.0),
        proj_row("2", "Mike", "Williams", "NYJ", "WR", 3.0),
    ]
    index = sleeper.PlayerIndex({}, rows)
    assert index.find(make_player("espn:p-1", "Mike Williams", "WR", "NYJ")) is None


def test_espn_id_wins_over_name_when_both_could_match():
    index = sleeper.PlayerIndex(DUMP, PROJECTIONS)
    found = index.find(make_player("espn:p-4360248", "Kyle Pitts Sr.", "TE", "ATL"))
    assert found is not None and found[1] == "espn_id"


# --------------------------------------------------------------------------------------
# Mapping + upsert
# --------------------------------------------------------------------------------------


def test_map_projection_keeps_all_three_scoring_formats():
    row = sleeper.map_projection(
        "espn:p-1",
        proj_row("1", "A", "B", "KC", "QB", 20.0, half=18.0, std=16.0),
        season=2026,
        week=1,
        match_tier="espn_id",
        fetched_at=FETCHED_AT,
    )
    assert (row.pts_ppr, row.pts_half_ppr, row.pts_std) == (20.0, 18.0, 16.0)
    assert row.source == "rotowire"
    assert '"pts_ppr": 20.0' in row.stats_json


async def test_fetch_and_upsert_writes_both_weekly_and_season_scopes(db):
    await seed(db, [("espn:p-3139477", "Patrick Mahomes", "QB", "KC")], week=4)
    client = FakeClient()

    async with db() as session:
        assert await sleeper.fetch_and_upsert(session, client) is None

    # Weekly first, then season (None) — both scopes, one pass each.
    assert client.calls == [4, None]
    async with db() as session:
        rows = (await session.execute(select(PlayerProjection))).scalars().all()
    assert sorted(r.week for r in rows) == [sleeper.SEASON_SCOPE, 4]
    assert {r.match_tier for r in rows} == {"espn_id"}


async def test_total_match_failure_is_reported_not_swallowed(db):
    """An empty projection column looks the same as "no data this week"; a total miss
    means the feed shape or the season is wrong and belongs on the refresh-runs row."""
    await seed(db, [("espn:p-999999", "Nobody Here", "WR", "BUF")])
    async with db() as session:
        error = await sleeper.fetch_and_upsert(session, FakeClient())
    assert error is not None and "matched 0 of 1" in error


# --------------------------------------------------------------------------------------
# The ESPN athlete-id bridge
# --------------------------------------------------------------------------------------

BRIDGE_DUMP = {
    "111": {"espn_id": 3139477, "yahoo_id": 30123},
    "222": {"espn_id": None, "yahoo_id": 40404},  # no ESPN side — nothing to bridge
    "333": {"espn_id": 4360248},  # no Yahoo side
}


def test_bridge_fills_espn_athlete_id_for_yahoo_players():
    player = make_player("yahoo:p-30123", "Patrick Mahomes", "QB", "KC")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 1
    assert player.espn_athlete_id == "3139477"


def test_bridge_skips_espn_players_who_already_carry_the_id():
    player = make_player("espn:p-3139477", "Patrick Mahomes", "QB", "KC")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 0
    assert player.espn_athlete_id is None


def test_bridge_skips_defenses():
    """Sleeper keys a defense by team abbreviation, and ESPN has no athlete for one."""
    player = make_player("yahoo:p-100", "Seahawks D/ST", "DST", "SEA")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 0
    assert player.espn_athlete_id is None


def test_bridge_is_idempotent():
    player = make_player("yahoo:p-30123", "Patrick Mahomes", "QB", "KC")
    sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player])
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 0


def test_bridge_leaves_a_player_with_no_espn_side_alone():
    player = make_player("yahoo:p-40404", "Someone Else", "WR", "BUF")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 0
    assert player.espn_athlete_id is None
