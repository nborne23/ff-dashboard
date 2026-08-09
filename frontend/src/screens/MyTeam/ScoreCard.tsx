// Ported from design/screen-myteam.jsx's ScoreCard. Actual/projected totals
// are the sum of the starters' RosterSlot points (bench doesn't count toward
// the weekly score); "games left" counts starters whose game hasn't started
// or is in progress (game_state "pre" | "in" — design.md D12's GameState).

import { ActivityRing, IconBolt } from "../../components/primitives";
import { useChangedValuePulse } from "../../hooks/useChangedValuePulse";
import type { RosterSlot } from "../../types/api";

export interface ScoreCardProps {
  starters: RosterSlot[];
  week: number;
}

export function ScoreCard({ starters, week }: ScoreCardProps) {
  const actual = starters.reduce((sum, s) => sum + s.actual_points, 0);
  const proj = starters.reduce((sum, s) => sum + s.proj_points, 0);
  const scorePulse = useChangedValuePulse(actual);
  const gamesLeft = starters.filter((s) => s.game_state === "pre" || s.game_state === "in").length;
  const pct = proj > 0 ? actual / proj : 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>
          Score
        </span>
        <span className="ts">Wk {week}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="metric" style={{ fontSize: 40, marginBottom: 4 }} {...scorePulse}>
            {actual.toFixed(1)}
            <span className="unit">pts</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--exercise)", fontWeight: 600 }}>
            Projected{" "}
            <span className="num" style={{ color: "var(--exercise)" }}>
              {proj.toFixed(1)}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            <span className="num">{gamesLeft}</span> games left
          </div>
        </div>
        <ActivityRing
          size={88}
          stroke={9}
          tracks={[{ value: pct, color: "#FF2D55" }]}
          label={`${Math.round(pct * 100)}%`}
        />
      </div>
    </div>
  );
}
