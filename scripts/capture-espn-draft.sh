#!/usr/bin/env bash
# Capture the ESPN payloads the Draft Assistant needs to be designed against.
#
# Usage:
#   ./capture-espn-draft.sh <LEAGUE_ID> '<SWID>' '<espn_s2>'
#
# SWID / espn_s2: Chrome DevTools -> Application -> Cookies -> fantasy.espn.com
# SWID includes the curly braces, e.g. '{1A2B3C4D-...}'
set -euo pipefail

LEAGUE_ID="${1:?league id required}"
SWID="${2:?SWID required}"
ESPN_S2="${3:?espn_s2 required}"
YEAR="${YEAR:-2026}"
BASE="https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUT="$(cd "$(dirname "$0")" && pwd)/espn-capture"
mkdir -p "$OUT"

echo "-> league settings + draft detail + teams"
curl -sS -b "SWID=${SWID}; espn_s2=${ESPN_S2}" \
  "${BASE}/seasons/${YEAR}/segments/0/leagues/${LEAGUE_ID}?view=mDraftDetail&view=mSettings&view=mTeam" \
  -o "${OUT}/league_draftdetail.json"

echo "-> full player universe (kona_player_info, 1200 players w/ ownership+ADP)"
curl -sS -b "SWID=${SWID}; espn_s2=${ESPN_S2}" \
  -H 'x-fantasy-filter: {"players":{"limit":1200,"sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"PPR"}}}' \
  "${BASE}/seasons/${YEAR}/segments/0/leagues/${LEAGUE_ID}?view=kona_player_info" \
  -o "${OUT}/kona_player_info.json"

echo "-> public player index (players_wl — id/name/position/proTeam, no auth)"
curl -sS -H 'x-fantasy-filter: {"filterActive":{"value":true}}' \
  "${BASE}/seasons/${YEAR}/players?scoringPeriodId=0&view=players_wl" \
  -o "${OUT}/players_wl.json"

for f in "${OUT}"/*.json; do
  printf '%-28s %8s bytes  ' "$(basename "$f")" "$(wc -c <"$f" | tr -d ' ')"
  head -c 120 "$f"; echo
done
echo
echo "Captured to: ${OUT}"
