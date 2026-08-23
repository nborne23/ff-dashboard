// Task 3.10 — filled/unfilled starter slots from the league's REAL roster shape
// (backend/gridiron/api/draft.py's `_assign_roster_slots`), FLEX rendered as its own
// numbered slots, and NO kicker slot (this league starts zero -- the freed slot's
// handcuff/second-DST suggestion is surfaced as an advisory string by
// `Recommendations.tsx`, sourced from the same `no_kicker_advisory` heuristic).
// Bye-collision warning fires at 3+ projected STARTERS sharing a bye week (not the
// whole roster including bench) -- `roster.bye_collisions` is already computed that way
// server-side.

import { useDraftState } from "../../api/draft";
import { Skeleton } from "../../components/primitives";

export function RosterPanel() {
  const stateQuery = useDraftState();
  const data = stateQuery.data?.data;

  if (stateQuery.isLoading || !data) {
    return (
      <div className="card" data-testid="roster-skeleton" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={32} style={{ marginBottom: 8 }} />
        ))}
      </div>
    );
  }

  const { roster } = data;

  return (
    <div className="card" data-testid="roster-panel">
      <div className="section-label" style={{ fontSize: 16, marginBottom: 4 }}>
        My Roster
      </div>
      <div className="row-list">
        {roster.starters.map((slot) => (
          <div key={slot.slot} className="draft-row" style={{ minHeight: 44 }}>
            <span className="pill pos">{slot.slot}</span>
            {slot.filled && slot.player ? (
              <div className="player-info">
                <div className="player-name">{slot.player.name}</div>
                <div className="player-meta">
                  {[slot.player.nfl_team, slot.player.bye ? `Bye ${slot.player.bye}` : null]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </div>
              </div>
            ) : (
              <span className="muted">Empty</span>
            )}
          </div>
        ))}
      </div>

      {roster.bye_collisions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
          {roster.bye_collisions.map((collision) => (
            <div key={collision.bye} className="bye-warning" data-testid="bye-collision">
              Week {collision.bye}: {collision.count} starters share this bye —{" "}
              {collision.players.join(", ")}
            </div>
          ))}
        </div>
      )}

      {roster.bench.length > 0 && (
        <>
          <div className="section-label" style={{ fontSize: 13, marginTop: 16, marginBottom: 4 }}>
            Bench
          </div>
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            {roster.bench.map((c) => c.name).join(", ")}
          </p>
        </>
      )}
    </div>
  );
}
