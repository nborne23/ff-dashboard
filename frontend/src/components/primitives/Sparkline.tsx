// Sparkline (line + optional area). Ported 1:1 from design/primitives.jsx.

const DEFAULT_THICKNESS = 1.5;

function readSparkThickness(): number {
  if (typeof document === "undefined") return DEFAULT_THICKNESS;
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--spark-thick");
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : DEFAULT_THICKNESS;
}

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  thickness?: number;
  dots?: boolean;
  area?: boolean;
  yMin?: number;
  yMax?: number;
}

export function Sparkline({
  data,
  width = 140,
  height = 48,
  color = "#FF2D55",
  thickness,
  dots = false,
  area = false,
  yMin,
  yMax,
}: SparklineProps) {
  const t = thickness || readSparkThickness();
  const lo = yMin != null ? yMin : Math.min(...data);
  const hi = yMax != null ? yMax : Math.max(...data);
  const range = hi - lo || 1;
  const padX = 4;
  const padY = 4;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const points = data.map((y, i) => {
    const x = padX + (i / (data.length - 1)) * innerW;
    const yp = padY + innerH - ((y - lo) / range) * innerH;
    return [x, yp];
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  const lastPoint = points[points.length - 1];
  const areaPath = `${path} L${lastPoint[0]},${height - padY} L${padX},${height - padY} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      {area && <path d={areaPath} fill={color} fillOpacity="0.15" />}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={t}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {dots && points.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={t * 1.4} fill={color} />)}
    </svg>
  );
}
