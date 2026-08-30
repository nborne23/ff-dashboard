"""Pure functions mapping raw ESPN Fantasy API payloads into normalized `schemas` entities.

Per the fantasy-data-model spec's "Mapper purity" scenario, these functions perform no
I/O and throw on unknown slot codes so platform schema drift fails loud rather than
silently dropping a player. Internal ids follow the `{platform}:{platform_id}` pattern
from design.md D12, e.g. `espn:1234567` (League) and `espn:l-1234567-t-2` (Team).

Scope of each `raw` argument:
- `map_league(raw)`: the full league-detail response (`view=mSettings&view=mTeam`) —
  same shape returned by `EspnClient.get_league`.
- `map_team(raw, league_id)`: a single element of that payload's `teams[]` array.
  `manager_name` / `is_user_team` need the payload's `members[]` + the caller's stored
  SWID, which a single team dict doesn't carry — see `resolve_user_team_id` and
  `manager_name_for` below. `map_team` defaults those fields; the caller (services/
  fantasy_service, task 3.9) overlays them, same as the week-scoped `current_*` /
  `spark_last_6` / `accent_color` fields which live outside this league payload entirely.
- `map_roster(raw, week)` / `map_matchup(raw, week, user_team_id)`: the full
  roster+matchup response (`view=mRoster&view=mMatchupScore&view=mBoxscore`) — same
  shape returned by both `EspnClient.get_roster` and `get_matchup` (one shared call).
  `map_roster` walks every `schedule[]` entry's home *and* away side, so it returns
  every rostered player in the league for that week, each correctly tagged with its
  own team's internal id (no separate team_id parameter needed).
"""

from backend.gridiron import schemas
from backend.gridiron.platforms.espn.slot_table import UnknownSlotError, espn_slot_name

# ESPN's `defaultPositionId` -> our internal `Position` literal.
POSITION_MAP: dict[int, schemas.Position] = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DST",
}

# ESPN's `proTeamId` -> standard NFL abbreviation. Complete for all 32 clubs, derived
# from the public `players_wl` D/ST entries (each carries `proTeamId` + the club
# nickname), so board matching can key on NFL team without silently demoting every
# unmapped player to "FA". ESPN leaves ids 31/32 unused. Unknown ids still fall back
# to "FA". Abbreviations follow the draft board's convention (JAX, LV, WAS, NE, NO).
PRO_TEAM_MAP: dict[int, str] = {
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WAS",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}

# ESPN's `injuryStatus` -> our internal `InjuryStatus` literal. Anything unrecognized
# maps to `None` rather than raising — unlike slot codes, an unknown injury status
# isn't a "we mis-mapped a player" failure, just missing metadata.
INJURY_STATUS_MAP: dict[str, schemas.InjuryStatus] = {
    "ACTIVE": "ACTIVE",
    "QUESTIONABLE": "Q",
    "DOUBTFUL": "D",
    "OUT": "O",
    "INJURY_RESERVE": "IR",
    "PHYSICALLY_UNABLE_TO_PERFORM": "PUP",
}

# ESPN slot names (from slot_table.LINEUP_SLOT_MAP) that map straight through to the
# internal `Slot` vocabulary without numbering.
_DIRECT_SLOTS = {"QB", "TE", "DST", "K", "BN", "IR"}
# ESPN slot names that need positional numbering (RB -> RB1/RB2) by order of appearance.
#
# FLEX is numbered for the same reason RB and WR are: a lineup can hold several, and the
# starter maps in `map_matchup` are keyed by slot label — so an unnumbered FLEX collapses
# a three-flex lineup to one entry, dropping two starters from both the projection and
# the paired matchup slots.
_NUMBERED_SLOTS = {"RB", "WR", "FLEX", "OP"}

STAT_SOURCE_ACTUAL = 0
STAT_SOURCE_PROJECTED = 1


def _scoring_type(settings: dict) -> schemas.ScoringType:
    scoring_settings = settings.get("scoringSettings", {})
    for item in scoring_settings.get("scoringItems", []):
        if item.get("statId") == 53:  # receptions
            points = item.get("points", 0)
            if points == 1.0:
                return "ppr"
            if points == 0.5:
                return "half_ppr"
            if points == 0:
                return "standard"
            return "custom"
    return "standard"


def map_league(raw: dict) -> schemas.League:
    """Map a `view=mSettings&view=mTeam` league-detail response to `schemas.League`."""
    league_id = raw["id"]
    settings = raw.get("settings", {})
    return schemas.League(
        id=f"espn:{league_id}",
        platform="espn",
        platform_id=str(league_id),
        name=settings.get("name", ""),
        season=raw["seasonId"],
        team_count=settings.get("size", len(raw.get("teams", []))),
        scoring_type=_scoring_type(settings),
        current_week=raw["scoringPeriodId"],
    )


def resolve_user_team_id(raw: dict, swid: str) -> int | None:
    """Match `swid` against `members[].id`, then find the team whose `owners[]` contains it.

    Returns `None` if no team is owned by that SWID (e.g. credentials for a league the
    user isn't actually in). Pure lookup — no I/O — kept separate from `map_team` per
    this module's docstring.
    """
    for team in raw.get("teams", []):
        if swid in team.get("owners", []):
            return team["id"]
    return None


def manager_name_for(raw: dict, team_id: int) -> str:
    """Look up the display name of `team_id`'s (first) owner from `raw["members"]`."""
    members_by_id = {m["id"]: m for m in raw.get("members", [])}
    for team in raw.get("teams", []):
        if team["id"] != team_id:
            continue
        for owner_id in team.get("owners", []):
            member = members_by_id.get(owner_id)
            if member is not None:
                return member.get("displayName", "")
    return ""


def map_team(raw: dict, league_id: int | str) -> schemas.Team:
    """Map one element of `teams[]` to `schemas.Team`.

    `manager_name`/`is_user_team`/`rank.total` and the week-scoped `current_*`/
    `spark_last_6`/`accent_color` fields aren't derivable from a single team dict —
    see this module's docstring. They default here and are expected to be overlaid by
    the caller (fantasy_service, task 3.9), which has the full league + matchup context.
    """
    team_id = raw["id"]
    name = raw.get("name") or f"{raw.get('location', '')} {raw.get('nickname', '')}".strip()
    overall = raw.get("record", {}).get("overall", {})
    return schemas.Team(
        id=f"espn:l-{league_id}-t-{team_id}",
        league_id=f"espn:{league_id}",
        name=name,
        manager_name="",
        record=schemas.Record(
            w=overall.get("wins", 0), l=overall.get("losses", 0), t=overall.get("ties", 0)
        ),
        rank=schemas.Rank(current=raw.get("playoffSeed", 0), total=0),
        points_for=overall.get("pointsFor", 0.0),
        points_against=overall.get("pointsAgainst", 0.0),
        is_user_team=False,
        current_score=0.0,
        current_opp_score=0.0,
        current_opponent_name="",
        is_live=False,
        spark_last_6=[],
        accent_color="",
    )


def _map_player(player: dict) -> schemas.Player:
    player_id = player["id"]
    position = POSITION_MAP.get(player.get("defaultPositionId", -1))
    if position is None:
        raise UnknownSlotError(player.get("defaultPositionId", -1))
    injury_status = INJURY_STATUS_MAP.get(player.get("injuryStatus", ""))
    return schemas.Player(
        id=f"espn:p-{player_id}",
        name=player.get("fullName", ""),
        position=position,
        nfl_team=PRO_TEAM_MAP.get(player.get("proTeamId", 0), "FA"),
        nfl_opponent=None,
        nfl_game_id=None,
        headshot_url=f"/api/headshots/espn/{player_id}.png",
        bye_week=player.get("byeWeek"),
        injury_status=injury_status,
    )


def _player_points(player: dict, week: int, stat_source_id: int) -> float:
    for stat in player.get("stats", []):
        if stat.get("scoringPeriodId") == week and stat.get("statSourceId") == stat_source_id:
            return stat.get("appliedTotal", 0.0)
    return 0.0


def _internal_slot(lineup_slot_id: int, counters: dict[str, int]) -> schemas.Slot:
    """Translate one entry's `lineupSlotId` to the internal `Slot` vocabulary.

    `counters` is mutated in place, keyed by ESPN slot name, so `RB`/`WR` entries are
    numbered `RB1`/`RB2`/`WR1`/`WR2` in the order they appear in the roster — the
    fantasy-data-model spec's documented numbering rule.
    """
    espn_name = espn_slot_name(lineup_slot_id)
    if espn_name in _NUMBERED_SLOTS:
        counters[espn_name] = counters.get(espn_name, 0) + 1
        return f"{espn_name}{counters[espn_name]}"  # type: ignore[return-value]
    if espn_name in _DIRECT_SLOTS:
        return espn_name  # type: ignore[return-value]
    # A recognized ESPN slot (e.g. an IDP position) with no internal Slot translation.
    # Fail loud per the mapper-purity scenario rather than silently dropping the player.
    raise UnknownSlotError(lineup_slot_id)


def _build_roster_slots(side: dict, team_id: str, week: int) -> list[schemas.RosterSlot]:
    entries = side.get("rosterForCurrentScoringPeriod", {}).get("entries", [])
    counters: dict[str, int] = {}
    slots: list[schemas.RosterSlot] = []
    for entry in entries:
        slot = _internal_slot(entry["lineupSlotId"], counters)
        player_raw = entry["playerPoolEntry"]["player"]
        player = _map_player(player_raw)
        slots.append(
            schemas.RosterSlot(
                team_id=team_id,
                week=week,
                slot=slot,
                player=player,
                proj_points=_player_points(player_raw, week, STAT_SOURCE_PROJECTED),
                actual_points=_player_points(player_raw, week, STAT_SOURCE_ACTUAL),
                is_live=False,
                game_state=None,
                status_text="",
            )
        )
    return slots


def map_roster(raw: dict, week: int) -> list[schemas.RosterSlot]:
    """Map a `view=mRoster&view=mMatchupScore&view=mBoxscore` response to every rostered
    player across every team's `schedule[]` entry for `week` (see module docstring)."""
    league_id = raw["id"]
    slots: list[schemas.RosterSlot] = []
    for matchup in raw.get("schedule", []):
        for side_key in ("home", "away"):
            side = matchup.get(side_key)
            if side is None:
                continue
            team_id = f"espn:l-{league_id}-t-{side['teamId']}"
            slots.extend(_build_roster_slots(side, team_id, week))
    return slots


_STARTER_SLOTS_EXCLUDED = {"BN", "IR"}


def map_matchup(
    raw: dict, week: int, user_team_id: int
) -> tuple[schemas.Matchup, list[schemas.MatchupSlot]]:
    """Map the roster+matchup response to the `schedule[]` entry involving `user_team_id`.

    `MatchupSlot`s are built for starting slots only (bench/IR are excluded — pairing
    reserve players 1:1 across two rosters isn't meaningful), matched home-vs-away by
    internal slot label.
    """
    league_id = raw["id"]
    for entry in raw.get("schedule", []):
        home, away = entry.get("home"), entry.get("away")
        involves_user = (home and home.get("teamId") == user_team_id) or (
            away and away.get("teamId") == user_team_id
        )
        if not involves_user:
            continue

        home_team_id = f"espn:l-{league_id}-t-{home['teamId']}"
        away_team_id = f"espn:l-{league_id}-t-{away['teamId']}"
        home_slots = {
            s.slot: s
            for s in _build_roster_slots(home, home_team_id, week)
            if s.slot not in _STARTER_SLOTS_EXCLUDED
        }
        away_slots = {
            s.slot: s
            for s in _build_roster_slots(away, away_team_id, week)
            if s.slot not in _STARTER_SLOTS_EXCLUDED
        }

        matchup_id = f"espn:l-{league_id}-m-{entry['id']}-w-{week}"
        matchup = schemas.Matchup(
            id=matchup_id,
            league_id=f"espn:{league_id}",
            week=week,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_score=home.get("totalPoints", 0.0),
            away_score=away.get("totalPoints", 0.0),
            home_proj=sum(s.proj_points for s in home_slots.values()),
            away_proj=sum(s.proj_points for s in away_slots.values()),
            is_complete=entry.get("winner", "UNDECIDED") != "UNDECIDED",
        )
        matchup_slots = [
            schemas.MatchupSlot(
                matchup_id=matchup_id,
                slot=slot,
                home_player=home_slots[slot].player,
                away_player=away_slots[slot].player,
                home_pts=home_slots[slot].actual_points,
                away_pts=away_slots[slot].actual_points,
            )
            for slot in sorted(set(home_slots) & set(away_slots))
        ]
        return matchup, matchup_slots

    raise ValueError(f"no schedule entry found for user_team_id={user_team_id!r} in week {week}")
