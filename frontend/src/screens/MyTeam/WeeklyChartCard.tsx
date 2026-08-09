// Ported from design/screen-myteam.jsx's WeeklyChartCard ("Scoring Today").
// The prototype fakes 60 hour-buckets of intra-day scoring with Math.random.
// TODO(Phase 8): once the live NFL scoreboard poller lands, replace this
// with real intra-day scoring buckets (per design.md's live-refresh plan).
// Until then, `useTeam`'s starters only carry a single per-player total for
// the week, so each bar below is one starter rather than a time bucket — the
// visual (dashed reference line at the team's projected pace) stays faithful
// to the prototype without inventing data we don't have.

import { BarChart, IconBolt } from "../../components/primitives";
import type { RosterSlot } from "../../types/api";

export interface WeeklyChartCardProps {
  starters: RosterSlot[];
}

export function WeeklyChartCard({ starters }: WeeklyChartCardProps) {
  const actual = starters.reduce((sum, s) => sum + s.actual_points, 0);
  const proj = starters.reduce((sum, s) => sum + s.proj_points, 0);
  const data = starters.map((s) => ({ x: s.slot, y: s.actual_points }));
  const pace = starters.length > 0 ? proj / starters.length : 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>
          Scoring Today
        </span>
        <span className="ts">Live</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 8 }}>
        <span className="metric" style={{ fontSize: 28 }}>
          {actual.toFixed(1)}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          / {proj.toFixed(1)} pts
        </span>
      </div>
      {data.length > 0 ? (
        <BarChart
          data={data}
          height={120}
          color="var(--move)"
          refLineY={pace}
          refTint="var(--move-tint)"
          barWidth={16}
          barGap={6}
        />
      ) : (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", padding: "24px 0" }}>
          No starters set for this week
        </div>
      )}
    </div>
  );
}
