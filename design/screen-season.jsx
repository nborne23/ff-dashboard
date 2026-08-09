// Screen 4: Season Overview

function SeasonChart() {
  const max = Math.max(...SEASON.map(s => Math.max(s.score, s.opp))) * 1.05;
  const avg = SEASON.reduce((a, s) => a + s.score, 0) / SEASON.length;
  const W = 1100;
  const H = 240;
  const padTop = 20;
  const padBottom = 32;
  const padLeft = 40;
  const padRight = 16;
  const innerH = H - padTop - padBottom;
  const colW = (W - padLeft - padRight) / SEASON.length;
  const barW = colW * 0.55;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: "block" }}>
      {/* Y-axis goal line */}
      {[40, 80, 120].map(y => {
        const yp = padTop + innerH - (y / max) * innerH;
        return (
          <g key={y}>
            <line x1={padLeft} x2={W - padRight} y1={yp} y2={yp}
              stroke="var(--separator)" strokeWidth="0.5" />
            <text x={padLeft - 8} y={yp + 3} fontSize="10" fill="var(--text-secondary)" textAnchor="end">{y}</text>
          </g>
        );
      })}
      {/* Average dashed */}
      <line
        x1={padLeft} x2={W - padRight}
        y1={padTop + innerH - (avg / max) * innerH}
        y2={padTop + innerH - (avg / max) * innerH}
        stroke="var(--text-secondary)" strokeWidth="1" strokeDasharray="4 4" opacity="0.6"
      />
      <text
        x={W - padRight - 4}
        y={padTop + innerH - (avg / max) * innerH - 4}
        fontSize="10" fill="var(--text-secondary)" textAnchor="end"
      >avg {avg.toFixed(1)}</text>

      {/* Bars */}
      {SEASON.map((s, i) => {
        const x = padLeft + i * colW + (colW - barW) / 2;
        const h = (s.score / max) * innerH;
        const y = padTop + innerH - h;
        const opH = (s.opp / max) * innerH;
        const opY = padTop + innerH - opH;
        const color = s.w ? "var(--stand)" : "var(--move)";
        const opacity = s.current ? 1 : 0.85;
        return (
          <g key={i}>
            {/* Opponent ghost bar */}
            <rect x={x + barW * 0.55} y={opY} width={barW * 0.45} height={opH}
              fill="var(--bench)" opacity="0.35" rx="2" />
            <rect x={x} y={y} width={barW * 0.55} height={h}
              fill={color} opacity={opacity} rx="2" />
            {s.current && (
              <rect x={x - 1} y={padTop} width={barW + 2} height={innerH}
                fill="rgba(255,255,255,0.04)" rx="2" />
            )}
            <text x={x + barW / 2} y={H - padBottom + 14}
              fontSize="10" fill="var(--text-secondary)" textAnchor="middle"
              fontWeight={s.current ? 700 : 400}>
              {s.wk}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function HighlightCard({ accent, icon, label, value, sub }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: accent }}>{icon}</span>
        <span className="cat-label" style={{ color: accent }}>{label}</span>
      </div>
      <div className="metric" style={{ fontSize: 30, marginTop: 4 }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function RecordDonut() {
  const wins = SEASON.filter(s => s.w).length;
  const losses = SEASON.length - wins;
  const total = wins + losses;
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: 24 }}>
      <div className="card-header" style={{ alignSelf: "stretch" }}>
        <span className="cat-dot" style={{ background: "var(--stand)" }}>
          <IconShield size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--stand)" }}>Season Record</span>
      </div>
      <div style={{ position: "relative", margin: "12px 0" }}>
        <ActivityRing
          size={180}
          stroke={18}
          gap={4}
          tracks={[
            { value: wins / total, color: "var(--stand)" },
          ]}
        />
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 38, fontWeight: 700, letterSpacing: "-0.02em" }}>{wins}–{losses}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{Math.round(wins/total*100)}% win rate</div>
          </div>
        </div>
      </div>
      <div className="legend" style={{ marginTop: 8 }}>
        <span><span className="swatch" style={{ background: "var(--stand)" }} />Wins</span>
        <span><span className="swatch" style={{ background: "var(--bench)" }} />Losses</span>
      </div>
    </div>
  );
}

function WeekHistory() {
  return (
    <div className="card" style={{ padding: 0, maxHeight: 420, overflowY: "auto" }}>
      <div style={{ padding: "16px 16px 4px", fontSize: 11, color: "var(--text-secondary)", letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600 }}>
        Week-by-week
      </div>
      <div className="row-list">
        {[...SEASON].reverse().map((s, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "auto auto 1fr auto", gap: 12,
            padding: "12px 16px", alignItems: "center",
            background: s.current ? "rgba(255,45,85,0.06)" : "transparent",
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", width: 28 }}>W{s.wk}</div>
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: s.w ? "var(--stand)" : "var(--move)",
            }} />
            <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              <span style={{ color: "var(--text-secondary)" }}>vs</span> {s.oppName}
            </div>
            <div className="num" style={{ fontSize: 13, fontWeight: 600 }}>
              {s.score.toFixed(1)} <span style={{ color: "var(--text-secondary)", margin: "0 2px" }}>–</span> {s.opp.toFixed(1)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SeasonScreen() {
  return (
    <>
      <h1 className="large-title">Season</h1>
      <p className="large-subtitle">Highland Bombers · 2025</p>

      <div className="card" style={{ marginBottom: 24, padding: "20px 16px 12px" }}>
        <div className="card-header" style={{ padding: "0 8px" }}>
          <span className="cat-dot" style={{ background: "var(--move)" }}>
            <IconBolt size={9} />
          </span>
          <span className="cat-label" style={{ color: "var(--move)" }}>Weekly Scores</span>
          <span className="ts">All weeks · cyan = win, pink = loss</span>
        </div>
        <SeasonChart />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "4fr 4fr 4fr", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>Highlights</div>
          <HighlightCard
            accent="var(--live)"
            icon={<IconFlame size={9} />}
            label="Win Streak"
            value="3 weeks"
            sub="W12, W13, W14 — longest streak this season"
          />
          <HighlightCard
            accent="var(--move)"
            icon={<IconBolt size={9} />}
            label="Season High"
            value="124.6 pts"
            sub="Week 3 vs Mom's Spaghetti"
          />
          <HighlightCard
            accent="var(--exercise)"
            icon={<IconStar size={9} />}
            label="Most Started"
            value="P. Mahomes"
            sub="14 starts · 18.4 avg pts"
          />
        </div>
        <div>
          <div className="section-label">Record</div>
          <RecordDonut />
        </div>
        <div>
          <div className="section-label">History</div>
          <WeekHistory />
        </div>
      </div>
    </>
  );
}

Object.assign(window, { SeasonScreen });
