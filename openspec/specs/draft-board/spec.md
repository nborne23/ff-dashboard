# draft-board Specification

## Purpose
TBD - created by archiving change add-draft-assistant. Update Purpose after archive.
## Requirements
### Requirement: Board data model

The system SHALL persist the user's hand-built ranking board in `board_players`, `board_tiers`, `board_heuristics`, and `board_id_overrides` tables. Array- and object-valued fields (`flags`, `injury_tags`, `analyst_takes`) SHALL be stored as JSON in `TEXT` columns and SHALL NOT be queried with SQLite-only JSON operators, preserving the scaffold's dialect-neutrality rule.

#### Scenario: Player record fields

- **WHEN** a player is imported from `draft_board/players.json`
- **THEN** the row carries `name`, `normalized_name`, `position`, `nfl_team`, `bye`, `adp`, `adp_rank`, `adp_round`, `adp_pick`, `overall_tier`, `positional_tier`, `risk`, `risk_score`, `rookie`, `out_for_season`, `note`, `thesis`, `take_in_round`, `sleeper_category`, `catalyst`, `format_fit`, `flags`, `injury_tags`, and `analyst_takes`, with fields absent from the source record stored as NULL.

#### Scenario: take_in_round accepts ranges

- **WHEN** `take_in_round` is parsed
- **THEN** both the simple form (`"Rd 4"`) and the range form (`"Rd 2-3"`, `"Rd 9-10"`) are accepted without error. The field is display-only and no scoring term reads it.

#### Scenario: Curated unpriced-risk column

- **WHEN** the board is imported
- **THEN** each player carries an `unpriced_risk` boolean that is **curated, not derived**. `strategy_rules.json` defines `adp_delta = expert_rank − adp_rank`, but `expert_rank` is absent from the export, and neither `take_in_round − adp_round` nor the `FADE` flag substitutes for it — both fail on the two players the board's own spec names as the canonical cases. The column is seeded by a one-time human pass over the players at `risk_score >= 4` and is the sole gate for the recommender's risk penalty.

#### Scenario: Nullable ADP

- **WHEN** a source record has no `adp` (4 of the 149 records)
- **THEN** `adp`, `adp_rank`, `adp_round`, and `adp_pick` are stored as NULL, the player remains in the draftable pool, and the recommender's value term contributes 0 for that player rather than raising.

#### Scenario: Tier labels normalized

- **WHEN** the import encounters `tier_label` and `positional_tier_label`, which repeat verbatim across every player sharing a tier
- **THEN** each distinct label is written once to `board_tiers` keyed by `(scope, position, tier)` where `scope` is `"overall"` or `"positional"`, and `board_players` references the tier by number only.

#### Scenario: Heuristics are addressable by id

- **WHEN** `strategy_rules.json` is imported
- **THEN** each entry in `heuristics` becomes a `board_heuristics` row keyed by its `id` (`draft_the_tier`, `flex_pressure`, `no_kicker`, `elite_te_window`, `qb_wait`, `dst_last`, `handcuff_own_studs`, `bye_stacking`, `injury_discount`), and the positional cliffs, value calc, and slot plan are persisted alongside them.

### Requirement: DST extraction from the source workbook

The system SHALL extract the 12 defenses from the `DST` worksheet of `2026_Draft_Board.xlsx`, which are absent from `players.json`. Extraction SHALL use only the Python standard library (`zipfile` + `xml.etree`); no spreadsheet dependency SHALL be added.

#### Scenario: Inline-string cells parsed

- **WHEN** the DST worksheet is read
- **THEN** cells marked `t="inlineStr"` are resolved from their `<is><t>` children rather than the shared-strings table, and the `Defense`, `Bye`, `ADP`, `Rd.Pk`, `Risk`, and `Note` columns are mapped onto `board_players` rows with `position='DST'`, NULL `overall_tier`, and NULL `positional_tier`.

#### Scenario: Header and commentary rows skipped

- **WHEN** the worksheet contains a header row and a single-cell commentary row above the data
- **THEN** both are skipped and exactly 12 defense rows are produced.

### Requirement: Idempotent board import

The system SHALL provide a re-runnable import that loads the JSON board, the DST tab, and the ESPN player universe. Running the import twice against unchanged inputs SHALL produce an identical database state.

#### Scenario: Re-import is idempotent

- **WHEN** the import runs a second time with unchanged source files
- **THEN** no duplicate `board_players` rows are created, row count remains 161, and previously-resolved `espn_player_id` values are unchanged.

#### Scenario: Overrides survive re-import

- **WHEN** the import runs after the user has manually resolved a match, creating a `board_id_overrides` row
- **THEN** that override is applied in preference to every automatic matching method and the resulting row records `match_method='override'` with `match_confidence=1.0`.

#### Scenario: Import is offline-capable for the board itself

- **WHEN** the ESPN player universe cannot be fetched
- **THEN** the board still imports in full with every `espn_player_id` NULL and `match_method='unmatched'`, and the import reports that matching was skipped rather than failing.

### Requirement: ESPN player-ID matching with confidence scoring

The system SHALL match each board entry to an ESPN `playerId` using ESPN's `players_wl` endpoint as the identity source, applying methods in strict precedence order and recording both the method and a confidence score on every row.

#### Scenario: Name normalization

- **WHEN** a name is prepared for matching
- **THEN** it is NFKD-folded, lowercased, stripped of punctuation and of generational suffixes (`Jr`, `Sr`, `II`, `III`, `IV`), and internal whitespace is collapsed.

#### Scenario: Matching precedence

- **WHEN** matching runs for a board entry
- **THEN** methods are attempted in order and the first hit wins: `override` (1.0), `exact` on normalized name + position + NFL team (1.0), `team_changed` on normalized name + position (0.9), `name_only` on normalized name (0.8), `fuzzy` via `difflib.SequenceMatcher` ratio ≥ 0.88 within the same position (0.6), otherwise `unmatched` (0.0).

#### Scenario: Defenses matched by team, never by name

- **WHEN** a `position='DST'` entry is matched
- **THEN** matching keys on the NFL team abbreviation against ESPN entries with `defaultPositionId == 16`, and name-based methods are not attempted.

#### Scenario: Ambiguous match is not silently chosen

- **WHEN** a method produces more than one candidate ESPN player
- **THEN** no `espn_player_id` is assigned, the entry is recorded as `unmatched`, and every candidate is listed in the QA report for human resolution.

### Requirement: Match QA gate

The system SHALL surface every unresolved or low-confidence match and SHALL prevent the Draft screen from entering live mode until they are resolved. A silently unmatched player never greys out when drafted and continues to be recommended, which is undetectable from the UI.

#### Scenario: Import produces a QA report

- **WHEN** the import completes
- **THEN** it reports total entries, counts per `match_method`, and the full list of entries at confidence < 0.9 with their candidate ESPN players.

#### Scenario: Live mode gated on resolution

- **WHEN** the user opens the Draft screen while any board entry has `match_confidence < 0.9`
- **THEN** the screen presents the resolution list instead of live mode, and manual board browsing and mark-drafted remain fully available.

#### Scenario: Resolution is permanent

- **WHEN** the user confirms or corrects a match in the resolution list
- **THEN** a `board_id_overrides` row is written, the `board_players` row is updated to `match_method='override'` with confidence 1.0, and the decision survives every subsequent re-import.

### Requirement: Board data-quality constraints

The system SHALL honor the known-bad-data constraints documented in the board's own specification rather than treating every field as trustworthy.

#### Scenario: Injury tags are advisory only

- **WHEN** `injury_tags` are used anywhere in the system
- **THEN** they are used only for search and display, and no recommendation heuristic — in particular `handcuff_own_studs` — keys off them, because they are keyword-derived from note prose and demonstrably wrong (Jahmyr Gibbs carries `mcl` because his note mentions another player's MCL sprain).

#### Scenario: out_for_season is corrected, not trusted

- **WHEN** the export marks a player `out_for_season`
- **THEN** a curated per-player correction file overrides it, because the flag is keyword-derived from note prose exactly as `injury_tags` is, and is far more consequential — it removes a player from the draftable pool entirely. Nico Collins (HOU WR1, ADP 21.5) was flagged out because his own note describes *Jayden Higgins* tearing an ACL. A genuinely-out player has also dropped out of ADP data, which is the signal the seed pass uses.

#### Scenario: Platform bye weeks win

- **WHEN** a board `bye` disagrees with the ESPN `Player.bye_week` for the same player
- **THEN** the ESPN value is authoritative for bye-collision warnings and the discrepancy is logged at import time.

#### Scenario: Incomplete flags reported, not assumed away

- **WHEN** the import encounters a player with `risk_score >= 4` and an empty `flags` array
- **THEN** the player is listed in the import report, because the export is known to omit flags that the note prose contradicts — Jeremiyah Love and Alec Pierce both carry empty `flags` despite their notes reading "Let someone else pay" and "Hard fade" respectively. The `FADE` scoring term consequently under-fires, and correcting it requires the user to re-export the board.

#### Scenario: Analyst attribution preserves accuracy tier

- **WHEN** an `analyst_takes` entry is displayed
- **THEN** its `source` is rendered together with its `verified_accuracy` flag, so measured-accuracy analysts are visually distinguishable from popular-but-unverified ones.

