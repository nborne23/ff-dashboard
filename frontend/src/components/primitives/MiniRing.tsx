// Tiny ring for arrow indicator (e.g. "Move →"). Ported 1:1 from
// design/primitives.jsx.

export interface MiniRingProps {
  size?: number;
  stroke?: number;
  value?: number;
  color?: string;
  icon?: "arrow" | "up";
}

export function MiniRing({
  size = 30,
  stroke = 4,
  value = 0.6,
  color = "#FF2D55",
  icon = "arrow",
}: MiniRingProps) {
  const r = size / 2 - stroke / 2;
  const c = 2 * Math.PI * r;
  return (
    <div
      style={{
        position: "relative",
        width: size,
        height: size,
        display: "inline-grid",
        placeItems: "center",
      }}
    >
      <svg
        width={size}
        height={size}
        style={{ transform: "rotate(-90deg)", position: "absolute", inset: 0 }}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeOpacity="0.2"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${c * value} ${c}`}
        />
      </svg>
      {icon === "arrow" && (
        <svg
          width={size * 0.45}
          height={size * 0.45}
          viewBox="0 0 24 24"
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ position: "relative" }}
        >
          <polyline points="5 12 19 12" />
          <polyline points="13 6 19 12 13 18" />
        </svg>
      )}
      {icon === "up" && (
        <svg
          width={size * 0.5}
          height={size * 0.5}
          viewBox="0 0 24 24"
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ position: "relative" }}
        >
          <polyline points="6 14 12 8 18 14" />
        </svg>
      )}
    </div>
  );
}
