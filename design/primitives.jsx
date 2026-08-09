// GridIron — SVG icons + chart primitives. Globals exported at bottom.

// ============ Icons (SF-Symbol-feel, line weight ~1.75) ============

const Icon = ({ children, size = 18, stroke = "currentColor", fill = "none" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={stroke}
       strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);

const IconDashboard = (p) => (
  <Icon {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Icon>
);
const IconTeams = (p) => (
  <Icon {...p}>
    <circle cx="9" cy="8" r="3.2" />
    <circle cx="17" cy="9" r="2.4" />
    <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" />
    <path d="M14 19c.4-2.4 2-4 4-4 1.6 0 2.8.7 3.5 2" />
  </Icon>
);
const IconMatchups = (p) => (
  <Icon {...p}>
    <path d="M5 4h4l1.5 5L8 13l2 7H5" />
    <path d="M19 4h-4l-1.5 5L16 13l-2 7h5" />
  </Icon>
);
const IconSeason = (p) => (
  <Icon {...p}>
    <path d="M3 20V8m5 12V4m5 16v-9m5 9V12" />
  </Icon>
);
const IconSettings = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1A1.7 1.7 0 0 0 20.9 10H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Icon>
);
const IconChevR = (p) => (
  <Icon {...p}>
    <polyline points="9 6 15 12 9 18" />
  </Icon>
);
const IconArrowL = (p) => (
  <Icon {...p}>
    <polyline points="15 6 9 12 15 18" />
  </Icon>
);
const IconArrowR = (p) => (
  <Icon {...p}>
    <polyline points="9 6 15 12 9 18" />
  </Icon>
);
const IconRefresh = (p) => (
  <Icon {...p}>
    <path d="M21 12a9 9 0 1 1-3-6.7" />
    <polyline points="21 4 21 9 16 9" />
  </Icon>
);
const IconUp = (p) => (
  <Icon {...p}>
    <polyline points="6 14 12 8 18 14" />
  </Icon>
);
const IconFootball = ({ size = 18, color = "#FF2D55" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M4 12c0-4.4 3.6-8 8-8s8 3.6 8 8-3.6 8-8 8-8-3.6-8-8z"
      stroke={color} strokeWidth="1.75" transform="rotate(-30 12 12)" />
    <path d="M9 12h6M11 9.5v5M13 9.5v5"
      stroke={color} strokeWidth="1.5" strokeLinecap="round" transform="rotate(-30 12 12)" />
  </svg>
);
const IconCalendar = (p) => (
  <Icon {...p}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </Icon>
);
const IconShield = (p) => (
  <Icon {...p}>
    <path d="M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6l8-3z" />
  </Icon>
);
const IconBolt = (p) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <polygon points="13 2 4 14 11 14 9 22 20 10 13 10 15 2" />
  </Icon>
);
const IconStar = (p) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <polygon points="12 2 15 9 22 10 17 15 18 22 12 19 6 22 7 15 2 10 9 9" />
  </Icon>
);
const IconFlame = (p) => (
  <Icon {...p}>
    <path d="M12 3c1 3 4 4 4 8a4 4 0 1 1-8 0c0-2 1-3 1-5 1 1 3 1 3-3z" />
  </Icon>
);
const IconCheck = (p) => (
  <Icon {...p}>
    <polyline points="5 12 10 17 19 7" />
  </Icon>
);
const IconX = (p) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);
const IconPlus = (p) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);
const IconLock = (p) => (
  <Icon {...p}>
    <rect x="5" y="11" width="14" height="9" rx="2" />
    <path d="M8 11V7a4 4 0 1 1 8 0v4" />
  </Icon>
);


// ============ Activity Ring ============
// Concentric rings like Apple Fitness. Pass tracks: [{value: 0..1, color}]
function ActivityRing({ size = 88, stroke = 9, tracks = [], gap = 3, label, sublabel }) {
  const rings = tracks.length;
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
              <circle cx={size/2} cy={size/2} r={r} fill="none"
                stroke={t.color} strokeOpacity="0.18" strokeWidth={stroke} />
              <circle cx={size/2} cy={size/2} r={r} fill="none"
                stroke={t.color} strokeWidth={stroke} strokeLinecap="round"
                strokeDasharray={`${c*filled} ${c}`} />
            </g>
          );
        })}
      </svg>
      {(label || sublabel) && (
        <div className="ring-center">
          {label && <div style={{ fontSize: size * 0.22, fontWeight: 700, lineHeight: 1 }}>{label}</div>}
          {sublabel && <div style={{ fontSize: size * 0.11, color: "var(--text-secondary)", marginTop: 2 }}>{sublabel}</div>}
        </div>
      )}
    </div>
  );
}

// Tiny ring for arrow indicator (e.g. "Move →")
function MiniRing({ size = 30, stroke = 4, value = 0.6, color = "#FF2D55", icon = "arrow" }) {
  const r = size/2 - stroke/2;
  const c = 2 * Math.PI * r;
  return (
    <div style={{ position: "relative", width: size, height: size, display: "inline-grid", placeItems: "center" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)", position: "absolute", inset: 0 }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeOpacity="0.2" strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={`${c*value} ${c}`} />
      </svg>
      {icon === "arrow" && (
        <svg width={size*0.45} height={size*0.45} viewBox="0 0 24 24" fill="none" stroke={color}
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ position: "relative" }}>
          <polyline points="5 12 19 12" />
          <polyline points="13 6 19 12 13 18" />
        </svg>
      )}
      {icon === "up" && (
        <svg width={size*0.5} height={size*0.5} viewBox="0 0 24 24" fill="none" stroke={color}
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ position: "relative" }}>
          <polyline points="6 14 12 8 18 14" />
        </svg>
      )}
    </div>
  );
}

// ============ Bar Chart (Move-style — dense, thin, dashed reference line) ============
function BarChart({
  data,                      // [{x: label, y: number}]
  height = 140,
  color = "#FF2D55",
  refLineY,                  // number: where to draw dashed line
  refLineLabel,
  refTint = "rgba(255,45,85,0.35)",
  axisLabels = true,
  barWidth = 4,
  barGap = 2,
  yMax,
  showAxisGoal,              // string e.g. "Goal 420"
}) {
  const max = yMax || Math.max(...data.map(d => d.y), refLineY || 0) * 1.05;
  const padTop = 12;
  const padBottom = axisLabels ? 18 : 6;
  const padLeft = 0;
  const padRight = 0;
  const innerH = height - padTop - padBottom;
  const totalBarW = data.length * barWidth + (data.length - 1) * barGap;

  return (
    <div className="chart-frame" style={{ height }}>
      <svg width="100%" height={height} preserveAspectRatio="none"
        viewBox={`0 0 ${Math.max(totalBarW, 100)} ${height}`}
        style={{ display: "block" }}>
        {/* Dashed reference line */}
        {refLineY != null && (
          <g>
            <line
              x1="0" x2={Math.max(totalBarW, 100)}
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
          return (
            <rect key={i} x={x} y={y} width={barWidth} height={h}
              fill={color} rx="1" />
          );
        })}
      </svg>
      {/* Axis labels overlay (using flex so they stay readable at any width) */}
      {axisLabels && (
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--text-secondary)",
          marginTop: -16,
          padding: "0 2px",
          fontVariantNumeric: "tabular-nums",
        }}>
          {data.filter((_, i) => i % Math.ceil(data.length / 6) === 0 || i === data.length-1).map((d, i) => (
            <span key={i}>{d.x}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ============ Sparkline (line + optional area) ============
function Sparkline({
  data,                  // numbers
  width = 140,
  height = 48,
  color = "#FF2D55",
  thickness,             // px
  dots = false,
  area = false,
  yMin, yMax,
}) {
  const t = thickness || parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--spark-thick")) || 1.5;
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
  const areaPath = path + ` L${points[points.length-1][0]},${height-padY} L${padX},${height-padY} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      {area && <path d={areaPath} fill={color} fillOpacity="0.15" />}
      <path d={path} fill="none" stroke={color} strokeWidth={t} strokeLinecap="round" strokeLinejoin="round" />
      {dots && points.map(([x,y], i) => (
        <circle key={i} cx={x} cy={y} r={t * 1.4} fill={color} />
      ))}
    </svg>
  );
}

// ============ Horizontal bar (for "vs league median") ============
function HorizBar({ value, max, color = "#FF2D55", height = 6, refValue }) {
  const pct = Math.min(1, value / max);
  return (
    <div style={{ position: "relative", height, background: "rgba(255,255,255,0.06)", borderRadius: 999 }}>
      <div style={{
        position: "absolute", inset: 0,
        width: `${pct * 100}%`,
        background: color,
        borderRadius: 999,
      }} />
      {refValue != null && (
        <div style={{
          position: "absolute", top: -3, bottom: -3,
          left: `${(refValue / max) * 100}%`,
          width: 1.5, background: "var(--text-secondary)",
        }} />
      )}
    </div>
  );
}

// ============ Week-day rings cluster (topbar) ============
function DayRings({ days, today }) {
  // days: [{letter, rings: [{value, color}]}]
  return (
    <div className="week-days">
      {days.map((d, i) => (
        <div key={i} className={"day-cell" + (i === today ? " today" : "")}>
          <span className="letter">{d.letter}</span>
          <ActivityRing size={20} stroke={2.5} gap={1} tracks={d.rings} />
        </div>
      ))}
    </div>
  );
}

// Export to globals
Object.assign(window, {
  Icon, IconDashboard, IconTeams, IconMatchups, IconSeason, IconSettings,
  IconChevR, IconArrowL, IconArrowR, IconRefresh, IconUp, IconFootball,
  IconCalendar, IconShield, IconBolt, IconStar, IconFlame, IconCheck, IconX,
  IconPlus, IconLock,
  ActivityRing, MiniRing, BarChart, Sparkline, HorizBar, DayRings,
});
