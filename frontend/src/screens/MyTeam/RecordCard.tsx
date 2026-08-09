// Ported from design/screen-myteam.jsx's RecordCard — cumulative W/L
// sparkline (+1 per win, -1 per loss, running sum) plus a W/L pill grid.
// Sparkline needs >= 2 points (it divides by `data.length - 1`), so a
// same-week-1 team with 0-1 games played gets a text fallback instead.

import { IconShield, Sparkline } from "../../components/primitives";
import { ordinal } from "../Dashboard/ordinal";
import type { SeasonWeek, Team } from "../../types/api";

export interface RecordCardProps {
  recordHistory: SeasonWeek[];
  team: Team;
}

export function RecordCard({ recordHistory, team }: RecordCardProps) {
  const cumulative = recordHistory.reduce<number[]>((acc, w) => {
    acc.push((acc[acc.length - 1] ?? 0) + (w.is_win ? 1 : -1));
    return acc;
  }, []);

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--stand)" }}>
          <IconShield size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--stand)" }}>
          Record
        </span>
        <span className="ts">Season</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
        <span className="metric" style={{ fontSize: 32 }}>
          W {team.record.w}–{team.record.l}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          · {ordinal(team.rank.current)} place
        </span>
      </div>
      {cumulative.length >= 2 ? (
        <Sparkline
          data={cumulative}
          width={280}
          height={48}
          color="var(--stand)"
          dots
          thickness={2}
        />
      ) : (
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          Not enough games played yet
        </div>
      )}
      <div style={{ display: "flex", gap: 4, marginTop: 12, flexWrap: "wrap" }}>
        {recordHistory.map((w) => (
          <div
            key={w.week}
            title={`Wk ${w.week}`}
            style={{
              width: 14,
              height: 14,
              borderRadius: 3,
              background: w.is_win ? "rgba(100,210,255,0.85)" : "rgba(255,45,85,0.7)",
              display: "grid",
              placeItems: "center",
              fontSize: 9,
              fontWeight: 700,
              color: "rgba(0,0,0,0.6)",
            }}
          >
            {w.is_win ? "W" : "L"}
          </div>
        ))}
      </div>
    </div>
  );
}
