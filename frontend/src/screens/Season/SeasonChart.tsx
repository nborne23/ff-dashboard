// Ported from design/screen-season.jsx's SeasonChart — the SVG is copied
// near-verbatim (same viewBox, paddings, gridlines) mapped onto the real
// SeasonWeek shape (design.md D12): score/opp_score/is_win/is_current/week
// in place of the prototype's score/opp/w/current/wk.

import type { SeasonWeek } from "../../types/api";

const W = 1100;
const H = 240;
const PAD_TOP = 20;
const PAD_BOTTOM = 32;
const PAD_LEFT = 40;
const PAD_RIGHT = 16;
const INNER_H = H - PAD_TOP - PAD_BOTTOM;

export interface SeasonChartProps {
  weeks: SeasonWeek[];
}

export function SeasonChart({ weeks }: SeasonChartProps) {
  if (weeks.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--text-secondary)" }}>
        No weeks played yet
      </div>
    );
  }

  const max = Math.max(...weeks.map((s) => Math.max(s.score, s.opp_score))) * 1.05 || 1;
  const avg = weeks.reduce((a, s) => a + s.score, 0) / weeks.length;
  const colW = (W - PAD_LEFT - PAD_RIGHT) / weeks.length;
  const barW = colW * 0.55;
  const avgY = PAD_TOP + INNER_H - (avg / max) * INNER_H;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: "block" }}>
      {[40, 80, 120].map((y) => {
        const yp = PAD_TOP + INNER_H - (y / max) * INNER_H;
        return (
          <g key={y}>
            <line
              x1={PAD_LEFT}
              x2={W - PAD_RIGHT}
              y1={yp}
              y2={yp}
              stroke="var(--separator)"
              strokeWidth="0.5"
            />
            <text
              x={PAD_LEFT - 8}
              y={yp + 3}
              fontSize="10"
              fill="var(--text-secondary)"
              textAnchor="end"
            >
              {y}
            </text>
          </g>
        );
      })}

      <line
        x1={PAD_LEFT}
        x2={W - PAD_RIGHT}
        y1={avgY}
        y2={avgY}
        stroke="var(--text-secondary)"
        strokeWidth="1"
        strokeDasharray="4 4"
        opacity="0.6"
      />
      <text
        x={W - PAD_RIGHT - 4}
        y={avgY - 4}
        fontSize="10"
        fill="var(--text-secondary)"
        textAnchor="end"
      >
        avg {avg.toFixed(1)}
      </text>

      {weeks.map((s, i) => {
        const x = PAD_LEFT + i * colW + (colW - barW) / 2;
        const h = (s.score / max) * INNER_H;
        const y = PAD_TOP + INNER_H - h;
        const opH = (s.opp_score / max) * INNER_H;
        const opY = PAD_TOP + INNER_H - opH;
        const color = s.is_win ? "var(--stand)" : "var(--move)";
        const opacity = s.is_current ? 1 : 0.85;
        return (
          <g key={s.week}>
            <rect
              x={x + barW * 0.55}
              y={opY}
              width={barW * 0.45}
              height={opH}
              fill="var(--bench)"
              opacity="0.35"
              rx="2"
            />
            <rect
              x={x}
              y={y}
              width={barW * 0.55}
              height={h}
              fill={color}
              opacity={opacity}
              rx="2"
            />
            {s.is_current && (
              <rect
                x={x - 1}
                y={PAD_TOP}
                width={barW + 2}
                height={INNER_H}
                fill="rgba(255,255,255,0.04)"
                rx="2"
              />
            )}
            <text
              x={x + barW / 2}
              y={H - PAD_BOTTOM + 14}
              fontSize="10"
              fill="var(--text-secondary)"
              textAnchor="middle"
              fontWeight={s.is_current ? 700 : 400}
            >
              {s.week}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
