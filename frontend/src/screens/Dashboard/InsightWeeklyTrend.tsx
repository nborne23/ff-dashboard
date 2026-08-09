// Ported from design/screen-dashboard.jsx's InsightWeeklyTrend. The
// prototype hardcodes a 14-week sample array and slices the last 6; here we
// compute the same shape from real data — the per-week average of every
// team's `spark_last_6` (each entry already represents "last 6 weeks ending
// at the current week" per Team's D12 shape).

import { IconBolt, Sparkline } from "../../components/primitives";
import type { Team } from "../../types/api";
import { WEEKS_SHOWN, computeWeekLabels, computeWeeklyAverages } from "./weeklyTrend";

export interface InsightWeeklyTrendProps {
  teams: Team[];
  week: number;
}

export function InsightWeeklyTrend({ teams, week }: InsightWeeklyTrendProps) {
  const averages = computeWeeklyAverages(teams);
  const avg = averages.length === 0 ? 0 : averages.reduce((sum, v) => sum + v, 0) / averages.length;
  const delta =
    averages.length >= 2 ? averages[averages.length - 1] - averages[averages.length - 2] : 0;
  const labels = computeWeekLabels(week, averages.length);
  const up = delta >= 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>
          Weekly Trend
        </span>
        <span className="ts">Last {WEEKS_SHOWN} weeks</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
        <span className="metric" style={{ fontSize: 28 }}>
          {avg.toFixed(1)}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>avg pts/wk</span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 12,
            color: up ? "var(--exercise)" : "var(--move)",
            fontWeight: 600,
          }}
        >
          {up ? "↗" : "↘"} {delta >= 0 ? "+" : ""}
          {delta.toFixed(1)}
        </span>
      </div>
      <Sparkline
        data={averages}
        width={280}
        height={64}
        color="var(--move)"
        dots
        area
        thickness={2}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 4,
          fontSize: 11,
          color: "var(--text-secondary)",
        }}
      >
        {labels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </div>
  );
}
