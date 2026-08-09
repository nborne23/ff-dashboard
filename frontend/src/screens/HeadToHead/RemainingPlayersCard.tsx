// Ported from design/screen-h2h.jsx's "Remaining Players" card. The
// prototype's per-slot subline ("WR1, TE, MNF rolling") isn't derivable from
// the real data: MatchupSlot (design.md D12) has no per-player game-state
// field, only the already-oriented counts in `remaining` from useTeamH2H.

import { IconFlame } from "../../components/primitives";

export interface RemainingPlayersCardProps {
  mine: number;
  theirs: number;
}

export function RemainingPlayersCard({ mine, theirs }: RemainingPlayersCardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--live)" }}>
          <IconFlame size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--live)" }}>
          Remaining Players
        </span>
        <span className="ts">In progress</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 24, marginTop: 8 }}>
        <div>
          <div
            style={{
              fontSize: 11,
              color: "var(--move)",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Mine
          </div>
          <div className="metric" style={{ fontSize: 36 }}>
            {mine}
            <span className="unit">players</span>
          </div>
        </div>
        <div style={{ width: 0.5, alignSelf: "stretch", background: "var(--separator)" }} />
        <div>
          <div
            style={{
              fontSize: 11,
              color: "var(--stand)",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Theirs
          </div>
          <div className="metric" style={{ fontSize: 36 }}>
            {theirs}
            <span className="unit">players</span>
          </div>
        </div>
      </div>
    </div>
  );
}
