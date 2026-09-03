"""Pure Yahoo raw-JSON -> normalized-entity mappers.

Per the fantasy-data-model spec, mappers are the only code with knowledge of Yahoo's
platform-specific shapes: no I/O, translate Yahoo's slot/position vocabulary into the
internal one, and fail loud (`MapperError`) on schema drift rather than silently guessing.

Yahoo's JSON is deeply nested — collections are `{"count": N, "0": {...}, ...}` and a single
resource's fields are spread across an array of small dicts (sometimes one level of list
nesting deeper for `team`/`league`/`player`, which carry many optional sub-resources). See
`_yahoo_json.py` for the shared flatten/collection helpers used here and in `client.py`.
"""

import hashlib
import logging

from backend.gridiron import schemas
from backend.gridiron.platforms.yahoo._yahoo_json import (
    collection_items,
    find_subresource,
    flatten,
    truthy,
)

logger = logging.getLogger("uvicorn.error")


class MapperError(Exception):
    """Raised when a Yahoo payload doesn't match the shape/vocabulary a mapper expects (an
    unrecognized roster slot code, a missing sub-resource, ...) — fail loud on platform
    schema drift rather than silently producing bad data."""


# Yahoo roster slot codes -> internal `Slot` vocabulary (backend/gridiron/schemas/common.py).
# RB/WR get numbered per the spec ("RB1/RB2", "WR1/WR2"); everything else maps 1:1 or
# renames (W/R/T -> FLEX, DEF -> DST).
_SLOT_MAP = {
    "QB": "QB",
    "TE": "TE",
    "K": "K",
    "DEF": "DST",
    "BN": "BN",
    "IR": "IR",
}
# Yahoo codes that map to a numbered internal slot. RB/WR keep their own names; the flex
# codes are renamed as well as numbered ("W/R/T" -> FLEX1/FLEX2/..., "Q/W/R/T" -> OP1/...).
# Numbering the flex matters for the same reason it does on the ESPN side: several flex
# starters sharing one label collapse when the matchup pairing keys by slot.
_NUMBERED_SLOTS = ("RB", "WR")
_NUMBERED_RENAMES = {"W/R/T": "FLEX", "Q/W/R/T": "OP"}

# Yahoo player `display_position` -> internal `Position` vocabulary. Yahoo uses "DEF" here
# too; everything else already matches.
_POSITION_MAP = {"DEF": "DST"}
_VALID_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}

# Yahoo's player `status` codes -> internal `InjuryStatus`. Yahoo OMITS the field entirely
# for a healthy player, so a missing/empty value legitimately means `ACTIVE`; an
# unrecognized one does not, and is mapped to `None` (see `_map_injury_status`).
#
# `IR-R` (return-designated) and `IR-NFI` are distinct Yahoo codes that both collapse to
# the coarser designation we model; `NA` is Yahoo's "not active" (inactive for the game).
_INJURY_MAP: dict[str, str] = {
    "Q": "Q",
    "D": "D",
    "O": "O",
    "IR": "IR",
    "IR-R": "IR",
    "IR-NFI": "NFI",
    "NFI-A": "NFI",
    "NFI-R": "NFI",
    "PUP": "PUP",
    "PUP-P": "PUP",
    "PUP-R": "PUP",
    "DTD": "DTD",
    "SUSP": "SUSP",
    "NA": "O",
}

# Yahoo's league-level `scoring_type` is a FORMAT axis ("head" head-to-head, "point"
# head-to-head points, "roto" rotisserie) — not a PPR axis. PPR-ness actually lives in
# `settings.stat_modifiers`, which the discovery endpoints this scaffold calls don't fetch.
# This is a documented best-effort approximation for the league picker UI, not a precise
# translation; unknown/unrecognized values fall back to "custom" rather than raising, since
# the spec only mandates raising on unknown *slot* codes.
_SCORING_TYPE_MAP = {"head": "standard", "point": "ppr", "roto": "custom"}


def _translate_slot(code: str, counters: dict[str, int]) -> str:
    name = _NUMBERED_RENAMES.get(code)
    if name is not None:
        counters[name] = counters.get(name, 0) + 1
        return f"{name}{counters[name]}"
    if code in _NUMBERED_SLOTS:
        counters[code] = counters.get(code, 0) + 1
        return f"{code}{counters[code]}"
    if code in _SLOT_MAP:
        return _SLOT_MAP[code]
    raise MapperError(f"unknown yahoo roster slot code: {code!r}")


def _map_position(raw_position: str) -> str:
    position = _POSITION_MAP.get(raw_position, raw_position)
    if position not in _VALID_POSITIONS:
        raise MapperError(f"unknown yahoo player position: {raw_position!r}")
    return position


def _map_injury_status(raw_status: str | None) -> str | None:
    """Missing -> `ACTIVE`; unrecognized -> `None`.

    Those two cases used to share the `"ACTIVE"` answer, which meant any Yahoo code outside
    `_INJURY_MAP` was reported to the UI as a healthy player. That is the one wrong answer
    worth avoiding here, and it is the opposite of the rule the ESPN mapper already states
    for its own unknown codes.
    """
    if not raw_status:
        return "ACTIVE"
    status = _INJURY_MAP.get(raw_status.upper())
    if status is None:
        logger.warning("unmapped yahoo player status: %r", raw_status)
    return status


def _map_scoring_type(raw_scoring_type: str | None) -> str:
    return _SCORING_TYPE_MAP.get((raw_scoring_type or "").lower(), "custom")


def _league_key_from_team_key(team_key: str) -> str:
    """`{game_key}.l.{league_id}.t.{team_id}` -> `{game_key}.l.{league_id}`."""
    return team_key.rsplit(".t.", 1)[0]


def map_league(raw: dict) -> schemas.League:
    """`raw` is a single collection item's `{"league": [...]}` fragment, e.g.
    `leagues_collection["0"]` from `/users;.../games;.../leagues?format=json`."""
    try:
        fields = flatten(raw["league"])
        league_key = fields["league_key"]
        return schemas.League(
            id=f"yahoo:{league_key}",
            platform="yahoo",
            platform_id=league_key,
            name=fields["name"],
            season=int(fields["season"]),
            team_count=int(fields["num_teams"]),
            scoring_type=_map_scoring_type(fields.get("scoring_type")),
            current_week=int(fields["current_week"]),
        )
    except KeyError as exc:
        raise MapperError(f"yahoo league payload missing expected field: {exc}") from exc


def map_team(raw: dict, league_id: str) -> schemas.Team:
    """`raw` is a single collection item's `{"team": [...]}` fragment, e.g.
    `teams_collection["0"]` from `/league/{league_key}/teams?format=json`.

    The teams-list endpoint doesn't carry score/record/standings data (that requires a
    separate matchup/standings fetch), so those fields get neutral defaults here; a later
    enrichment step fills them in from `map_matchup` results.
    """
    try:
        fields = flatten(raw["team"])
        team_key = fields["team_key"]

        manager_name = ""
        managers = fields.get("managers") or []
        if managers and isinstance(managers[0], dict):
            manager_name = managers[0].get("manager", {}).get("nickname", "")

        accent_color = "#" + hashlib.md5(team_key.encode("utf-8")).hexdigest()[:6]  # noqa: S324

        return schemas.Team(
            id=f"yahoo:{team_key}",
            league_id=league_id,
            name=fields["name"],
            manager_name=manager_name,
            record=schemas.Record(w=0, l=0, t=0),
            rank=schemas.Rank(current=0, total=0),
            points_for=0.0,
            points_against=0.0,
            is_user_team=truthy(fields.get("is_owned_by_current_login", 0)),
            current_score=0.0,
            current_opp_score=0.0,
            current_opponent_name="",
            is_live=False,
            spark_last_6=[],
            accent_color=accent_color,
        )
    except KeyError as exc:
        raise MapperError(f"yahoo team payload missing expected field: {exc}") from exc


def map_roster(raw: dict, week: int) -> list[schemas.RosterSlot]:
    """`raw` is the full `/team/{team_key}/roster;week={N}/players/stats?format=json`
    response."""
    try:
        team_array = raw["fantasy_content"]["team"]
        team_fields = flatten(team_array[0])
        team_key = team_fields["team_key"]

        roster_root = find_subresource(team_array, "roster")
        players_root = roster_root["0"]["players"]

        counters: dict[str, int] = {}
        slots: list[schemas.RosterSlot] = []
        for item in collection_items(players_root):
            fields = flatten(item["player"])
            player_key = fields["player_key"]

            selected = flatten(fields["selected_position"])
            slot = _translate_slot(selected["position"], counters)

            actual_points = float((fields.get("player_points") or {}).get("total", 0) or 0)
            proj_points = float((fields.get("player_points_projected") or {}).get("total", 0) or 0)

            bye = fields.get("bye_weeks") or {}
            bye_week = int(bye["week"]) if bye.get("week") not in (None, "") else None

            player = schemas.Player(
                id=f"yahoo:{player_key}",
                name=fields.get("name", {}).get("full", ""),
                position=_map_position(fields["display_position"]),
                nfl_team=fields.get("editorial_team_abbr", ""),
                nfl_opponent=None,
                nfl_game_id=None,
                headshot_url=fields.get("image_url", ""),
                bye_week=bye_week,
                injury_status=_map_injury_status(fields.get("status")),
            )
            slots.append(
                schemas.RosterSlot(
                    team_id=f"yahoo:{team_key}",
                    week=week,
                    slot=slot,
                    player=player,
                    proj_points=proj_points,
                    actual_points=actual_points,
                    is_live=False,
                    game_state=None,
                    status_text="",
                )
            )
        return slots
    except KeyError as exc:
        raise MapperError(f"yahoo roster payload missing expected field: {exc}") from exc


def map_matchup(raw: dict, week: int) -> schemas.Matchup:
    """`raw` is the full `/team/{team_key}/matchups;weeks={N}?format=json` response."""
    try:
        team_array = raw["fantasy_content"]["team"]
        matchups_root = find_subresource(team_array, "matchups")
        matchup_items = collection_items(matchups_root)
        if not matchup_items:
            raise MapperError("yahoo matchup payload has no matchups")
        matchup = matchup_items[0]["matchup"]

        team_entries = collection_items(matchup["teams"])
        if len(team_entries) < 2:
            raise MapperError("yahoo matchup payload does not have two teams")

        # Yahoo doesn't label a "home"/"away" side for fantasy head-to-head matchups; index 0
        # is treated as "home" purely for a stable, deterministic ordering.
        parsed = []
        for entry in team_entries[:2]:
            team_parts = entry["team"]
            team_fields = flatten(team_parts[0])
            extra = flatten(team_parts[1:])
            points = extra.get("team_points") or {}
            proj = extra.get("team_projected_points") or {}
            parsed.append(
                {
                    "team_key": team_fields["team_key"],
                    "score": float(points.get("total", 0) or 0),
                    "proj": float(proj.get("total", 0) or 0),
                }
            )

        home, away = parsed
        league_key = _league_key_from_team_key(home["team_key"])
        status = str(matchup.get("status", ""))

        return schemas.Matchup(
            id=f"yahoo:{league_key}.mu.{week}",
            league_id=f"yahoo:{league_key}",
            week=week,
            home_team_id=f"yahoo:{home['team_key']}",
            away_team_id=f"yahoo:{away['team_key']}",
            home_score=home["score"],
            away_score=away["score"],
            home_proj=home["proj"],
            away_proj=away["proj"],
            is_complete=status.lower() == "postevent",
        )
    except KeyError as exc:
        raise MapperError(f"yahoo matchup payload missing expected field: {exc}") from exc
