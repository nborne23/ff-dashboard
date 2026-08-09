// Move-style bar chart — dense, thin, dashed reference line. Ported 1:1 from
// design/primitives.jsx.

export interface BarChartDatum {
  x: string;
  y: number;
}

export interface BarChartProps {
  data: BarChartDatum[];
  height?: number;
  color?: string;
  /** Where to draw the dashed reference line. */
  refLineY?: number;
  /** Reserved for parity with the prototype's props surface; not yet rendered. */
  refLineLabel?: string;
  refTint?: string;
  axisLabels?: boolean;
  barWidth?: number;
  barGap?: number;
  yMax?: number;
  /** Reserved for parity with the prototype's props surface; not yet rendered. */
  showAxisGoal?: string;
}

export function BarChart({
  data,
  height = 140,
  color = "#FF2D55",
  refLineY,
  refTint = "rgba(255,45,85,0.35)",
  axisLabels = true,
  barWidth = 4,
  barGap = 2,
  yMax,
}: BarChartProps) {
  const max = yMax || Math.max(...data.map((d) => d.y), refLineY || 0) * 1.05;
  const padTop = 12;
  const padBottom = axisLabels ? 18 : 6;
  const innerH = height - padTop - padBottom;
  const totalBarW = data.length * barWidth + (data.length - 1) * barGap;

  return (
    <div className="chart-frame" style={{ height }}>
      <svg
        width="100%"
        height={height}
        preserveAspectRatio="none"
        viewBox={`0 0 ${Math.max(totalBarW, 100)} ${height}`}
        style={{ display: "block" }}
      >
        {/* Dashed reference line */}
        {refLineY != null && (
          <g>
            <line
              x1="0"
              x2={Math.max(totalBarW, 100)}
              y1={padTop + innerH - (refLineY / max) * innerH}
              y2={padTop + innerH - (refLineY / max) * innerH}
              stroke={refTint}
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          </g>
        )}
        {/* Bars */}
        {data.map((d, i) => {
          const h = (d.y / max) * innerH;
          const x = i * (barWidth + barGap);
          const y = padTop + innerH - h;
          return <rect key={i} x={x} y={y} width={barWidth} height={h} fill={color} rx="1" />;
        })}
      </svg>
      {/* Axis labels overlay (using flex so they stay readable at any width) */}
      {axisLabels && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--text-secondary)",
            marginTop: -16,
            padding: "0 2px",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {data
            .filter((_, i) => i % Math.ceil(data.length / 6) === 0 || i === data.length - 1)
            .map((d, i) => (
              <span key={i}>{d.x}</span>
            ))}
        </div>
      )}
    </div>
  );
}
