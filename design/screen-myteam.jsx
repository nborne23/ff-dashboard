// Screen 2: My Team — roster table + side cards.

function PositionPill({ pos }) {
  return <span className="pill pos">{pos}</span>;
}

function RosterRow({ row, isBench }) {
  const live = row.live;
  const delta = (row.actual || 0) - row.proj;
  const initials = row.name.split(" ").map(n => n[0]).slice(0,2).join("");
  return (
    <tr className={live ? "live-row" : (isBench ? "bench-row" : "")}>
      <td style={{ width: 64, fontWeight: 700, fontSize: 13, color: isBench ? "var(--text-secondary)" : "var(--text-secondary)", letterSpacing: "0.05em" }}>
        {row.slot}
      </td>
      <td>
        <div className="player-cell">
          <div className="headshot">{initials}</div>
          <div className="player-info">
            <div className="player-info-row">
              <span className="player-name">{row.name}</span>
              <PositionPill pos={row.pos} />
            </div>
            <div className="player-meta">{row.team}</div>
          </div>
        </div>
      </td>
      <td style={{ width: 90 }} className="muted">{row.opp}</td>
      <td style={{ width: 140 }}>
        {live ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--live)", fontWeight: 600, fontSize: 12 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--live)", boxShadow: "0 0 6px var(--live)" }} />
            {row.status}
          </span>
        ) : row.status === "OUT" ? (
          <span style={{ color: "var(--espn)", fontWeight: 600, fontSize: 12 }}>OUT</span>
        ) : (
          <span className="muted" style={{ fontSize: 12 }}>{row.status}</span>
        )}
      </td>
      <td style={{ width: 88, textAlign: "right" }} className="num muted">{row.proj.toFixed(1)}</td>
      <td style={{ width: 88, textAlign: "right" }} className="num">
        {row.actual ? row.actual.toFixed(1) : "—"}
      </td>
      <td style={{ width: 80, textAlign: "right" }}>
        {row.actual && row.actual > 0 ? (
          <span className={"delta " + (delta > 0.05 ? "pos" : delta < -0.05 ? "neg" : "zero")}>
            {delta > 0 ? "+" : ""}{delta.toFixed(1)}
          </span>
        ) : <span className="muted">—</span>}
      </td>
    </tr>
  );
}

function RosterTable() {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="roster">
        <thead>
          <tr>
            <th style={{ width: 64 }}>Slot</th>
            <th>Player</th>
            <th>Opp</th>
            <th>Status</th>
            <th style={{ textAlign: "right" }}>Proj</th>
            <th style={{ textAlign: "right" }}>Actual</th>
            <th style={{ textAlign: "right" }}>+/–</th>
          </tr>
        </thead>
        <tbody>
          <tr className="section-row"><td colSpan={7}>Starters</td></tr>
          {ROSTER.map((r, i) => <RosterRow key={i} row={r} />)}
          <tr className="section-row"><td colSpan={7}>Bench</td></tr>
          {BENCH.map((r, i) => <RosterRow key={i} row={r} isBench />)}
        </tbody>
      </table>
    </div>
  );
}

function ScoreCard() {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>Score</span>
        <span className="ts">Wk 14</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="metric" style={{ fontSize: 40, marginBottom: 4 }}>78.4<span className="unit">pts</span></div>
          <div style={{ fontSize: 13, color: "var(--exercise)", fontWeight: 600 }}>
            Projected <span className="num" style={{ color: "var(--exercise)" }}>112.6</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
            <span className="num">5</span> games left
          </div>
        </div>
        <ActivityRing
          size={88}
          stroke={9}
          tracks={[{ value: 78.4 / 112.6, color: "#FF2D55" }]}
          label={`${Math.round((78.4/112.6)*100)}%`}
        />
      </div>
    </div>
  );
}

function WeeklyChartCard() {
  // Hour-by-hour scoring through gameday
  const data = [];
  for (let i = 0; i < 60; i++) {
    let v = 0;
    if (i > 8 && i < 22) v = Math.random() * 18 + 4;
    else if (i > 28 && i < 42) v = Math.random() * 22 + 6;
    else if (i > 44 && i < 56) v = Math.random() * 14 + 3;
    data.push({ x: "", y: v });
  }
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>Scoring Today</span>
        <span className="ts">Live</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 8 }}>
        <span className="metric" style={{ fontSize: 28 }}>78.4</span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>/ 112.6 pts</span>
      </div>
      <BarChart
        data={data}
        height={120}
        color="var(--move)"
        refLineY={112.6 / 60 * 1.5}
        refTint="var(--move-tint)"
        barWidth={3}
        barGap={2}
        axisLabels={false}
      />
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--text-secondary)" }}>
        <span>Thu</span><span>Sun 1pm</span><span>Sun 4pm</span><span>SNF</span><span>MNF</span>
      </div>
    </div>
  );
}

function RecordCard() {
  // Win/loss sparkline as +1/-1
  const wl = SEASON.map(s => s.w ? 1 : -1);
  const cum = [];
  let running = 0;
  wl.forEach(v => { running += v; cum.push(running); });
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--stand)" }}>
          <IconShield size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--stand)" }}>Record</span>
        <span className="ts">Season</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
        <span className="metric" style={{ fontSize: 32 }}>W 8–3</span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>· 2nd place</span>
      </div>
      <Sparkline data={cum} width={280} height={48} color="var(--stand)" dots thickness={2} />
      <div style={{ display: "flex", gap: 4, marginTop: 12, flexWrap: "wrap" }}>
        {SEASON.map((s, i) => (
          <div key={i} title={`Wk ${s.wk}`} style={{
            width: 14, height: 14, borderRadius: 3,
            background: s.w ? "rgba(100,210,255,0.85)" : "rgba(255,45,85,0.7)",
            display: "grid", placeItems: "center",
            fontSize: 9, fontWeight: 700, color: "rgba(0,0,0,0.6)",
          }}>{s.w ? "W" : "L"}</div>
        ))}
      </div>
    </div>
  );
}

function MyTeamScreen() {
  const [seg, setSeg] = React.useState("W14");
  const team = TEAMS[0];
  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 8 }}>
        <div>
          <h1 className="large-title">{team.name}</h1>
          <p className="large-subtitle" style={{ marginBottom: 0 }}>
            <PlatformPill platform={team.platform} /> &nbsp;&nbsp;{team.league} · {team.rank}
          </p>
        </div>
        <div style={{ marginLeft: "auto", marginBottom: 4 }}>
          <div className="segmented">
            {["W12","W13","W14","W15"].map(s => (
              <button key={s} className={seg === s ? "active" : ""} onClick={() => setSeg(s)}>{s}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="spacer-md" />
      <div className="dashboard-grid">
        <div>
          <div className="section-label" style={{ marginBottom: 12 }}>Roster</div>
          <RosterTable />
        </div>
        <div className="rail">
          <ScoreCard />
          <WeeklyChartCard />
          <RecordCard />
        </div>
      </div>
    </>
  );
}

Object.assign(window, { MyTeamScreen });
