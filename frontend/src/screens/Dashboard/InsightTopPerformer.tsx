// Ported from design/screen-dashboard.jsx's InsightTopPerformer.
//
// TODO(Phase 4 backend follow-up): the spec (design.md) implies "top
// performer" is a per-player stat (name, position, NFL team, points vs the
// league median at that position) computed server-side. No endpoint exposes
// that yet. Until it exists, `selectTopPerformerFallback` derives a
// client-side stand-in from `GET /api/teams` — the team with the highest
// `current_score` this week — so the card has real, live-updating content
// rather than static prototype numbers. Swap the selector for a real
// `/api/insights/top-performer`-style fetch once the backend adds it; the
// DOM below should not need to change.

import { HorizBar, IconBolt } from "../../components/primitives";
import type { Team } from "../../types/api";
import { median, selectTopPerformerFallback } from "./selectTopPerformer";

export interface InsightTopPerformerProps {
  teams: Team[];
  week: number;
  isLoading: boolean;
}

export function InsightTopPerformer({ teams, week, isLoading }: InsightTopPerformerProps) {
  const fallback = selectTopPerformerFallback(teams);
  const leagueMedian = median(teams.map((t) => t.current_score));
  const max = Math.max(30, Math.ceil(((fallback?.points ?? 0) + 10) / 10) * 10);
  const diff = fallback ? fallback.points - leagueMedian : 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>
          Top Performer
        </span>
        <span className="ts">Wk {week}</span>
      </div>

      {isLoading && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)", padding: "12px 0" }}>
          Loading…
        </div>
      )}

      {!isLoading && !fallback && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)", padding: "12px 0" }}>
          No data yet
        </div>
      )}

      {!isLoading && fallback && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <div className="headshot" style={{ width: 44, height: 44, fontSize: 13 }}>
              {fallback.initials}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{fallback.headline}</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{fallback.subline}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="metric" style={{ fontSize: 28 }}>
                {fallback.points.toFixed(1)}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>PTS</div>
            </div>
          </div>
          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 11,
                color: "var(--text-secondary)",
                marginBottom: 6,
              }}
            >
              <span>vs league median</span>
              <span className="tnum" style={{ color: "var(--move)" }}>
                {diff >= 0 ? "+" : ""}
                {diff.toFixed(1)}
              </span>
            </div>
            <HorizBar
              value={fallback.points}
              max={max}
              color="var(--move)"
              refValue={leagueMedian}
              height={8}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 10,
                color: "var(--text-secondary)",
                marginTop: 4,
              }}
            >
              <span>0</span>
              <span>median {leagueMedian.toFixed(1)}</span>
              <span>{max}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
