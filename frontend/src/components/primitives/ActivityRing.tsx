// Concentric rings like Apple Fitness. Ported 1:1 from design/primitives.jsx.

export interface ActivityRingTrack {
  value: number;
  color: string;
}

export interface ActivityRingProps {
  size?: number;
  stroke?: number;
  tracks?: ActivityRingTrack[];
  gap?: number;
  label?: string;
  sublabel?: string;
}

export function ActivityRing({
  size = 88,
  stroke = 9,
  tracks = [],
  gap = 3,
  label,
  sublabel,
}: ActivityRingProps) {
  const baseR = size / 2 - stroke / 2;
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {tracks.map((t, i) => {
          const r = baseR - i * (stroke + gap);
          if (r <= 0) return null;
          const c = 2 * Math.PI * r;
          const filled = Math.max(0, Math.min(1, t.value));
          return (
            <g key={i}>
              <circle
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={t.color}
                strokeOpacity="0.18"
                strokeWidth={stroke}
              />
              <circle
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={t.color}
                strokeWidth={stroke}
                strokeLinecap="round"
                strokeDasharray={`${c * filled} ${c}`}
              />
            </g>
          );
        })}
      </svg>
      {(label || sublabel) && (
        <div className="ring-center">
          {label && (
            <div style={{ fontSize: size * 0.22, fontWeight: 700, lineHeight: 1 }}>{label}</div>
          )}
          {sublabel && (
            <div style={{ fontSize: size * 0.11, color: "var(--text-secondary)", marginTop: 2 }}>
              {sublabel}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
