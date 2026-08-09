// Ported from design/screen-season.jsx's RecordDonut, driven by the real
// SeasonWeek[] from useTeamSeason instead of the prototype's static SEASON
// array.

import { ActivityRing, IconShield } from "../../components/primitives";
import type { SeasonWeek } from "../../types/api";

export interface RecordDonutProps {
  weeks: SeasonWeek[];
}

export function RecordDonut({ weeks }: RecordDonutProps) {
  const wins = weeks.filter((w) => w.is_win).length;
  const losses = weeks.length - wins;
  const total = wins + losses;
  const winPct = total > 0 ? Math.round((wins / total) * 100) : 0;

  return (
    <div
      className="card"
      style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: 24 }}
    >
      <div className="card-header" style={{ alignSelf: "stretch" }}>
        <span className="cat-dot" style={{ background: "var(--stand)" }}>
          <IconShield size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--stand)" }}>
          Season Record
        </span>
      </div>
      <div style={{ position: "relative", margin: "12px 0" }}>
        <ActivityRing
          size={180}
          stroke={18}
          gap={4}
          tracks={[{ value: total > 0 ? wins / total : 0, color: "var(--stand)" }]}
        />
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 38, fontWeight: 700, letterSpacing: "-0.02em" }}>
              {wins}–{losses}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
              {winPct}% win rate
            </div>
          </div>
        </div>
      </div>
      <div className="legend" style={{ marginTop: 8 }}>
        <span>
          <span className="swatch" style={{ background: "var(--stand)" }} />
          Wins
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--bench)" }} />
          Losses
        </span>
      </div>
    </div>
  );
}
