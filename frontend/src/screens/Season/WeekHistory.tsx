// Ported from design/screen-season.jsx's WeekHistory — reverse-chronological
// row list, current-week row tinted (matches design.md D12's is_current).

import type { SeasonWeek } from "../../types/api";

export interface WeekHistoryProps {
  weeks: SeasonWeek[];
}

export function WeekHistory({ weeks }: WeekHistoryProps) {
  const reversed = [...weeks].reverse();

  return (
    <div className="card" style={{ padding: 0, maxHeight: 420, overflowY: "auto" }}>
      <div
        style={{
          padding: "16px 16px 4px",
          fontSize: 11,
          color: "var(--text-secondary)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontWeight: 600,
        }}
      >
        Week-by-week
      </div>
      <div className="row-list">
        {reversed.length === 0 && (
          <div style={{ padding: 16, fontSize: 13, color: "var(--text-secondary)" }}>
            No weeks yet
          </div>
        )}
        {reversed.map((s) => (
          <div
            key={s.week}
            data-testid={s.is_current ? "week-history-current-row" : undefined}
            style={{
              display: "grid",
              gridTemplateColumns: "auto auto 1fr auto",
              gap: 12,
              padding: "12px 16px",
              alignItems: "center",
              background: s.is_current ? "rgba(255,45,85,0.06)" : "transparent",
            }}
          >
            <div
              style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", width: 28 }}
            >
              W{s.week}
            </div>
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: s.is_win ? "var(--stand)" : "var(--move)",
              }}
            />
            <div
              style={{
                fontSize: 13,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              <span style={{ color: "var(--text-secondary)" }}>vs</span> {s.opp_team_name}
            </div>
            <div className="num" style={{ fontSize: 13, fontWeight: 600 }}>
              {s.score.toFixed(1)}{" "}
              <span style={{ color: "var(--text-secondary)", margin: "0 2px" }}>–</span>{" "}
              {s.opp_score.toFixed(1)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
