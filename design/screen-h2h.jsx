// Screen 3: Head-to-Head

function H2HRings() {
  const myScore = 87.4;
  const oppScore = 71.2;
  const myProj = 112.6;
  const oppProj = 98.4;
  return (
    <div style={{ position: "relative", display: "inline-grid", placeItems: "center" }}>
      <ActivityRing
        size={200}
        stroke={16}
        gap={4}
        tracks={[
          { value: myScore / myProj, color: "var(--move)" },
          { value: oppScore / oppProj, color: "var(--stand)" },
        ]}
      />
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        <div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", letterSpacing: "0.06em", textTransform: "uppercase" }}>Lead</div>
          <div style={{ fontSize: 38, fontWeight: 700, letterSpacing: "-0.02em", color: "var(--move)" }} className="tnum">+16.2</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Q3 · 5 games left</div>
        </div>
      </div>
    </div>
  );
}

function H2HScreen() {
  const myTotal = H2H.reduce((a, r) => a + r.me.pts, 0);
  const oppTotal = H2H.reduce((a, r) => a + r.opp.pts, 0);
  return (
    <>
      <h1 className="large-title">Head-to-Head</h1>
      <p className="large-subtitle">Highland Bros Dynasty · Week 14</p>

      <div className="card" style={{ padding: "32px 24px", marginBottom: 24 }}>
        <div className="h2h-top">
          <div className="h2h-side me">
            <div className="name">HIGHLAND BOMBERS</div>
            <div className="score-big">87.4</div>
            <div className="record">8–3 · 2nd place</div>
          </div>
          <H2HRings />
          <div className="h2h-side opp">
            <div className="name">TOUCHDOWN CLUB</div>
            <div className="score-big">71.2</div>
            <div className="record">6–5 · 7th place</div>
          </div>
        </div>

        <div style={{ borderTop: "0.5px solid var(--separator)", paddingTop: 24, marginTop: 8 }}>
          <div className="three-stat">
            <div>
              <div className="stat-label" style={{ color: "var(--move)" }}>Points</div>
              <div className="stat-val">{myTotal.toFixed(1)}<span className="stat-unit">vs {oppTotal.toFixed(1)}</span></div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--exercise)" }}>Projected</div>
              <div className="stat-val">112.6<span className="stat-unit">vs 98.4</span></div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--stand)" }}>Win Prob.</div>
              <div className="stat-val">82<span className="stat-unit">%</span></div>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 24 }}>
        <table className="h2h-table">
          <thead>
            <tr>
              <th className="me">Highland Bombers</th>
              <th className="center">Slot</th>
              <th className="opp">Touchdown Club</th>
            </tr>
          </thead>
          <tbody>
            {H2H.map((row, i) => {
              const diff = row.me.pts - row.opp.pts;
              const tie = Math.abs(diff) < 0.05;
              return (
                <tr key={i}>
                  <td>
                    <div className="me-cell">
                      <div className="headshot">{row.me.name.split(". ")[1]?.[0] || "?"}</div>
                      <div className="player-info">
                        <div className="player-name">{row.me.name}</div>
                        <div className="player-meta">{row.me.pts.toFixed(1)} pts</div>
                      </div>
                    </div>
                  </td>
                  <td className="center">
                    <div className="pos-label">{row.pos}</div>
                    <span className={"diff-chip " + (tie ? "tie" : diff > 0 ? "pos" : "neg")}>
                      {tie ? "TIE" : (diff > 0 ? "+" : "") + diff.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    <div className="opp-cell">
                      <div className="headshot">{row.opp.name.split(". ")[1]?.[0] || "?"}</div>
                      <div className="player-info">
                        <div className="player-name">{row.opp.name}</div>
                        <div className="player-meta">{row.opp.pts.toFixed(1)} pts</div>
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div className="card">
          <div className="card-header">
            <span className="cat-dot" style={{ background: "var(--live)" }}>
              <IconFlame size={9} />
            </span>
            <span className="cat-label" style={{ color: "var(--live)" }}>Remaining Players</span>
            <span className="ts">In progress</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 24, marginTop: 8 }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--move)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Mine</div>
              <div className="metric" style={{ fontSize: 36 }}>3<span className="unit">players</span></div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>WR1, TE, MNF rolling</div>
            </div>
            <div style={{ width: 0.5, alignSelf: "stretch", background: "var(--separator)" }} />
            <div>
              <div style={{ fontSize: 11, color: "var(--stand)", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Theirs</div>
              <div className="metric" style={{ fontSize: 36 }}>5<span className="unit">players</span></div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>QB, RB1, FLEX, K, DST</div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="cat-dot" style={{ background: "var(--exercise)" }}>
              <IconCheck size={9} />
            </span>
            <span className="cat-label" style={{ color: "var(--exercise)" }}>Projected Final</span>
            <span className="ts">Confidence 82%</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 8 }}>
            <span className="metric" style={{ fontSize: 36 }}>118.4</span>
            <span className="vs" style={{ color: "var(--text-secondary)", fontSize: 18 }}>–</span>
            <span className="metric" style={{ fontSize: 36, color: "var(--text-secondary)" }}>105.2</span>
          </div>
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
              <span>Range: 102 – 134</span>
              <span className="num">+13.2</span>
            </div>
            <div style={{ position: "relative", height: 8, background: "rgba(255,255,255,0.06)", borderRadius: 999 }}>
              <div style={{
                position: "absolute", left: "20%", right: "12%", top: 0, bottom: 0,
                background: "linear-gradient(90deg, rgba(255,45,85,0.15), var(--move) 50%, rgba(255,45,85,0.15))",
                borderRadius: 999,
              }} />
              <div style={{
                position: "absolute", left: "53%", top: -4, bottom: -4, width: 2,
                background: "var(--text)", borderRadius: 1,
              }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-secondary)", marginTop: 4 }}>
              <span>floor</span><span>likely 118.4</span><span>ceiling</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { H2HScreen });
