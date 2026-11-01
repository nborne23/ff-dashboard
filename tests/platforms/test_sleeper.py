"""Sleeper projection ingest — the three matcher tiers, ambiguity, and scope encoding."""

from datetime import datetime

import httpx
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
    def __init__(self, dump=None, projections=None, by_week=None, fail_weeks=()):
        self._dump = DUMP if dump is None else dump
        self._proj = PROJECTIONS if projections is None else projections
        self._by_week = by_week or {}
        self._fail_weeks = set(fail_weeks)
        self.calls: list[int | None] = []

    async def get_players(self, session):
        return self._dump

    async def get_projections(self, season, week):
        self.calls.append(week)
        if week in self._fail_weeks:
            raise httpx.ConnectError("sleeper is down")
        return self._by_week.get(week, self._proj)

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

    # Weekly first, then season (None) — both scopes, one pass each. The daily pass over
    # the season's other weeks follows; see the tests at the bottom.
    assert client.calls[:2] == [4, None]
    async with db() as session:
        rows = (await session.execute(select(PlayerProjection))).scalars().all()
    scoped = [r for r in rows if r.week in (sleeper.SEASON_SCOPE, 4)]
    assert sorted(r.week for r in scoped) == [sleeper.SEASON_SCOPE, 4]
    assert {r.match_tier for r in scoped} == {"espn_id"}


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
    # No yahoo_id, but a name and team to match on — Sleeper's yahoo_id coverage is
    # patchy, and this is what the name+team fallback is for.
    "444": {"espn_id": 4426502, "first_name": "Brock", "last_name": "Bowers", "team": "LV"},
    # Two players sharing a name+team key: ambiguous, so neither may be used.
    "555": {"espn_id": 1, "first_name": "Josh", "last_name": "Allen", "team": "JAX"},
    "666": {"espn_id": 2, "first_name": "Josh", "last_name": "Allen", "team": "JAX"},
}


def test_bridge_fills_espn_athlete_id_for_yahoo_players():
    player = make_player("yahoo:p-30123", "Patrick Mahomes", "QB", "KC")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 1
    assert player.espn_athlete_id == "3139477"


def test_bridge_matches_a_real_yahoo_player_key():
    """A Yahoo `platform_id` is the full player key (`470.p.30123`) while Sleeper's
    `yahoo_id` is the bare trailing id. Matching on the whole key found nothing, so no
    Yahoo player was ever bridged and their injury badges had no detail behind them."""
    player = make_player("yahoo:470.p.30123", "Patrick Mahomes", "QB", "KC")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 1
    assert player.espn_athlete_id == "3139477"


def test_bridge_falls_back_to_name_and_team_when_the_dump_has_no_yahoo_id():
    player = make_player("yahoo:470.p.40878", "Brock Bowers", "TE", "LV")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 1
    assert player.espn_athlete_id == "4426502"


def test_bridge_drops_an_ambiguous_name_and_team_rather_than_guessing():
    player = make_player("yahoo:470.p.1", "Josh Allen", "DE", "JAX")
    assert sleeper.bridge_espn_athlete_ids(BRIDGE_DUMP, [player]) == 0
    assert player.espn_athlete_id is None


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


async def test_projections_are_filed_under_the_apps_current_week(db):
    """A league that hasn't drafted reports `current_week` 0. Picking a league arbitrarily
    and defaulting that 0 to 1 filed every weekly projection under week 1 while the read
    paths asked for the real current week, so the waivers screen's weekly axis was null on
    both platforms."""
    await seed(db, [("espn:p-3139477", "Patrick Mahomes", "QB", "KC")], week=0)
    async with db() as session:
        undrafted = await session.get(League, "espn:1")
        assert undrafted.current_week == 0
        session.add(
            League(
                id="espn:999",
                platform="espn",
                platform_id="999",
                name="Started League",
                season=undrafted.season,
                team_count=10,
                scoring_type="ppr",
                current_week=4,
            )
        )
        await session.commit()

    client = FakeClient()
    async with db() as session:
        await sleeper.fetch_and_upsert(session, client)
        rows = (await session.execute(select(PlayerProjection))).scalars().all()

    # The current week is asked for, and filed, as 4 — then the daily other-weeks pass.
    assert client.calls[:2] == [4, None]
    assert {sleeper.SEASON_SCOPE, 4} <= {r.week for r in rows}


# --------------------------------------------------------------------------------------
# The rest of the season, once a day
# --------------------------------------------------------------------------------------

MAHOMES = ("espn:p-3139477", "Patrick Mahomes", "QB", "KC")
ETIENNE = ("espn:p-4239996", "Travis Etienne Jr.", "RB", "JAX")


def week_feed(ppr):
    """A one-week feed where every player is projected for `ppr`, to tell weeks apart."""
    return [
        proj_row("111", "Patrick", "Mahomes", "KC", "QB", ppr),
        proj_row("222", "Travis", "Etienne", "JAX", "RB", ppr),
    ]


async def stored_points(db):
    async with db() as session:
        rows = (await session.execute(select(PlayerProjection))).scalars().all()
    return {(r.player_id, r.week): r.pts_ppr for r in rows}


async def seed_projection(db, player_id, week, ppr):
    async with db() as session:
        session.add(
            PlayerProjection(
                player_id=player_id,
                season=2026,
                week=week,
                source=sleeper.SOURCE,
                pts_ppr=ppr,
                match_tier="espn_id",
                fetched_at=FETCHED_AT,
            )
        )
        await session.commit()


async def test_first_run_fetches_every_other_week_of_the_season(db):
    """The player card's Game Log prints Proj Pts for every week, past and future, and
    the current-week path alone left all but one of them blank."""
    await seed(db, [MAHOMES], week=4)
    client = FakeClient(by_week={w: week_feed(float(w)) for w in range(1, 19)})

    async with db() as session:
        assert await sleeper.fetch_and_upsert(session, client) is None

    assert client.calls == [4, None, 1, 2, 3, *range(5, 19)]
    points = await stored_points(db)
    assert {week for _pid, week in points} == {sleeper.SEASON_SCOPE, *range(1, 19)}
    assert points[(MAHOMES[0], 12)] == 12.0


async def test_the_other_weeks_are_fetched_at_most_once_a_day(db):
    await seed(db, [MAHOMES], week=4)
    async with db() as session:
        await sleeper.fetch_and_upsert(session, FakeClient())

    again = FakeClient()
    async with db() as session:
        assert await sleeper.fetch_and_upsert(session, again) is None
    assert again.calls == [4, None]


async def test_a_future_week_is_refreshed(db):
    await seed(db, [MAHOMES], week=4)
    await seed_projection(db, MAHOMES[0], 9, 3.0)

    async with db() as session:
        await sleeper.fetch_and_upsert(session, FakeClient(by_week={9: week_feed(19.5)}))

    assert (await stored_points(db))[(MAHOMES[0], 9)] == 19.5


async def test_a_past_week_only_fills_gaps_and_is_skipped_when_full(db):
    """A past week keeps the number captured while it was current — what the app showed
    going into that game. Only a player missing from it is backfilled, and a week with
    nobody missing isn't fetched at all."""
    await seed(db, [MAHOMES, ETIENNE], week=4)
    await seed_projection(db, MAHOMES[0], 2, 3.0)  # week 2: Etienne missing
    await seed_projection(db, MAHOMES[0], 3, 3.0)  # week 3: both present
    await seed_projection(db, ETIENNE[0], 3, 3.0)
    client = FakeClient(by_week={w: week_feed(float(w)) for w in range(1, 19)})

    async with db() as session:
        await sleeper.fetch_and_upsert(session, client)

    assert 2 in client.calls and 3 not in client.calls
    points = await stored_points(db)
    assert points[(MAHOMES[0], 2)] == 3.0
    assert points[(ETIENNE[0], 2)] == 2.0
    assert points[(MAHOMES[0], 3)] == points[(ETIENNE[0], 3)] == 3.0


async def test_an_outage_on_another_week_keeps_the_current_week_and_retries(db):
    await seed(db, [MAHOMES], week=4)

    async with db() as session:
        assert await sleeper.fetch_and_upsert(session, FakeClient(fail_weeks={9})) is None

    points = await stored_points(db)
    assert (MAHOMES[0], 4) in points and (MAHOMES[0], sleeper.SEASON_SCOPE) in points
    # No daily marker was written, so the next tick tries the other weeks again.
    retry = FakeClient()
    async with db() as session:
        await sleeper.fetch_and_upsert(session, retry)
    assert 9 in retry.calls
