// Horizontal bar (for "vs league median"). Ported 1:1 from
// design/primitives.jsx.

export interface HorizBarProps {
  value: number;
  max: number;
  color?: string;
  height?: number;
  refValue?: number;
}

export function HorizBar({ value, max, color = "#FF2D55", height = 6, refValue }: HorizBarProps) {
  const pct = Math.min(1, value / max);
  return (
    <div
      style={{
        position: "relative",
        height,
        background: "rgba(255,255,255,0.06)",
        borderRadius: 999,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          width: `${pct * 100}%`,
          background: color,
          borderRadius: 999,
        }}
      />
      {refValue != null && (
        <div
          style={{
            position: "absolute",
            top: -3,
            bottom: -3,
            left: `${(refValue / max) * 100}%`,
            width: 1.5,
            background: "var(--text-secondary)",
          }}
        />
      )}
    </div>
  );
}
