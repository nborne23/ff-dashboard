// Task 4.6 — match resolution: shows every board entry below the 0.9 ESPN-match
// confidence gate (backend/gridiron/services/draft_matches.py, task 4.5) and lets a
// human resolve each by picking a candidate ESPN player, or recording "no ESPN match"
// when none fits.
//
// Live-mode ESPN features (phase 5, not built yet) are meant to be gated behind this
// list being empty, but THIS component is a visible, NON-BLOCKING status card — it
// renders alongside the rest of the Draft screen, never in front of it. Manual board
// browsing, mark-drafted, undo, and recommendations all stay fully usable regardless of
// what this shows; nothing here disables them (see Draft/index.tsx).
//
// The real committed board has 0 entries needing resolution (160 exact matches + 1
// team_changed at exactly 0.9, which is AT the gate, not below it) — the empty branch
// below renders an explicit "everything matched" state precisely so that common case
// never reads as still-loading or broken.

import { useState } from "react";

import { getApiErrorMessage } from "../../api/client";
import type { BoardMatchOut } from "../../api/draft";
import { MATCH_CONFIDENCE_THRESHOLD, useDraftMatches, useSetMatchOverride } from "../../api/draft";
import { Skeleton } from "../../components/primitives";
import { ErrorCard } from "../../components/shared/ErrorCard";

function MatchRow({ match }: { match: BoardMatchOut }) {
  const setOverride = useSetMatchOverride();
  const [error, setError] = useState<string | null>(null);

  function resolve(espnPlayerId: number | null) {
    setError(null);
    setOverride.mutate(
      { boardPlayerName: match.board_player_name, espnPlayerId },
      { onError: (err) => setError(getApiErrorMessage(err, "Couldn't save that match.")) },
    );
  }

  return (
    <div className="match-resolution-row" data-testid="match-resolution-row">
      <div className="match-resolution-row-header">
        <span className="player-name">{match.board_player_name}</span>
        <span className="pill pos">{match.match_method}</span>
        <span className="pill loss">{Math.round(match.match_confidence * 100)}%</span>
      </div>

      {match.candidates.length > 0 ? (
        <div className="match-resolution-candidates">
          {match.candidates.map((candidate) => (
            <button
              key={candidate.espn_player_id}
              type="button"
              className="btn primary"
              onClick={() => resolve(candidate.espn_player_id)}
              disabled={setOverride.isPending}
              aria-label={`Match ${match.board_player_name} to ${candidate.full_name}, ${candidate.position} ${candidate.nfl_team}`}
            >
              {candidate.full_name} · {candidate.position} {candidate.nfl_team}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted match-resolution-no-candidates">No ESPN candidates found.</p>
      )}

      <button
        type="button"
        className="btn"
        onClick={() => resolve(null)}
        disabled={setOverride.isPending}
        aria-label={`Record no ESPN match for ${match.board_player_name}`}
      >
        No ESPN match
      </button>
      {error && (
        <span style={{ color: "var(--espn)", fontSize: 11 }} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function MatchResolution() {
  const matchesQuery = useDraftMatches();

  if (matchesQuery.isError) {
    return (
      <ErrorCard
        error={matchesQuery.error}
        fallbackMessage="Couldn't load ESPN match status."
        onRetry={() => void matchesQuery.refetch()}
        testId="match-resolution-error"
      />
    );
  }

  if (matchesQuery.isLoading || !matchesQuery.data) {
    return (
      <div className="card" data-testid="match-resolution-skeleton" aria-hidden="true">
        <Skeleton width="60%" height={18} />
      </div>
    );
  }

  const {
    matches,
    below_threshold_count: belowCount,
    method_counts: methodCounts,
  } = matchesQuery.data.data;
  const needsResolution = matches.filter((m) => m.match_confidence < MATCH_CONFIDENCE_THRESHOLD);
  const methodSummary = Object.entries(methodCounts)
    .sort(([, a], [, b]) => b - a)
    .map(([method, count]) => `${count} ${method}`)
    .join(", ");

  if (belowCount === 0) {
    return (
      <div className="match-resolution-banner ok" data-testid="match-resolution-empty">
        <span className="match-resolution-title">All board players matched to ESPN</span>
        {methodSummary && <p className="muted match-resolution-summary">{methodSummary}</p>}
      </div>
    );
  }

  return (
    <div className="match-resolution-banner" data-testid="match-resolution-list">
      <div className="match-resolution-title">
        {belowCount === 1
          ? "1 player needs ESPN match resolution"
          : `${belowCount} players need ESPN match resolution`}
      </div>
      <p className="muted match-resolution-summary">
        ESPN-live features stay off until these are resolved — board browsing, mark-drafted, undo,
        and recommendations are unaffected.
      </p>
      {needsResolution.map((match) => (
        <MatchRow key={match.board_player_name} match={match} />
      ))}
    </div>
  );
}
