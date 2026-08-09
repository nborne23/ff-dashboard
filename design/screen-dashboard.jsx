// Screen 1: Dashboard

function PlatformPill({ platform }) {
  if (platform === "yahoo") return <span className="pill yahoo">YAHOO</span>;
  return <span className="pill espn">ESPN</span>;
}

function TeamCard({ team }) {
  const winning = team.score >= team.oppScore;
  return (
    <div className="team-card">
      <div className="left">
        <div className="top-row">
          <span className="team-name">{team.name}</span>
          <PlatformPill platform={team.platform} />
          {team.live && <span className="live-dot" />}
        </div>
        <div className="score">
          <span style={{ color: winning ? "var(--text)" : "var(--text-secondary)" }}>{team.score.toFixed(1)}</span>
          <span className="vs">–</span>
          <span style={{ color: winning ? "var(--text-secondary)" : "var(--text)" }}>{team.oppScore.toFixed(1)}</span>
        </div>
        <div className="sub">
          <span>vs {team.opponent}</span>
          <span style={{ color: "var(--separator)" }}>•</span>
          <span>{team.record}</span>
          <span style={{ color: "var(--separator)" }}>•</span>
          <span>{team.rank}</span>
        </div>
      </div>
      <div className="spark">
        <Sparkline data={team.spark} width={140} height={56} color={team.accent} dots area />
      </div>
    </div>
  );
}

function InsightTopPerformer() {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>Top Performer</span>
        <span className="ts">Wk 14</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div className="headshot" style={{ width: 44, height: 44, fontSize: 13 }}>BR</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Bijan Robinson</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>RB · ATL · Highland Bombers</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="metric" style={{ fontSize: 28 }}>24.1</div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>PTS</div>
        </div>
      </div>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-secondary)", marginBottom: 6 }}>
          <span>vs RB median</span>
          <span className="tnum" style={{ color: "var(--move)" }}>+11.6</span>
        </div>
        <HorizBar value={24.1} max={30} color="var(--move)" refValue={12.5} height={8} />
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-secondary)", marginTop: 4 }}>
          <span>0</span>
          <span>median 12.5</span>
          <span>30</span>
        </div>
      </div>
    </div>
  );
}

function InsightWeeklyTrend() {
  const data = [88, 71, 124, 88, 71, 96, 110, 64, 105, 92, 117, 81, 99, 87];
  const last6 = data.slice(-6);
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--move)" }}>
          <IconBolt size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--move)" }}>Weekly Trend</span>
        <span className="ts">Last 6 weeks</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
        <span className="metric" style={{ fontSize: 28 }}>92.7</span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>avg pts/wk</span>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--exercise)", fontWeight: 600 }}>↗ +4.2</span>
      </div>
      <Sparkline data={last6} width={280} height={64} color="var(--move)" dots area thickness={2} />
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 11, color: "var(--text-secondary)" }}>
        <span>W9</span><span>W10</span><span>W11</span><span>W12</span><span>W13</span><span>W14</span>
      </div>
    </div>
  );
}

function InsightLiveGames() {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--live)" }}>
          <IconFlame size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--live)" }}>Live Games</span>
        <span className="ts">3 active</span>
      </div>
      {LIVE_GAMES.map((g, i) => {
        const isLive = g.q.startsWith("Q") || g.q.startsWith("OT");
        const isFinal = g.q === "FINAL";
        return (
          <div key={i} className="game-row">
            <div>
              <div className="matchup">
                <span className="num">{g.away}</span> @ <span className="num">{g.home}</span>
                {g.mine > 0 && (
                  <span style={{ marginLeft: 6, fontSize: 10, color: "var(--text-secondary)" }}>
                    · {g.mine} {g.mine > 1 ? "players" : "player"}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: isLive ? "var(--live)" : "var(--text-secondary)", marginTop: 1, fontWeight: 600 }}>
                {isLive && <span style={{
                  display: "inline-block", width: 5, height: 5, borderRadius: "50%",
                  background: "var(--live)", marginRight: 4, verticalAlign: "middle",
                  boxShadow: "0 0 6px var(--live)",
                }} />}
                {g.q}
              </div>
            </div>
            {!g.q.startsWith("Mon") && !g.q.startsWith("Sun") && (
              <div className="gscore tnum">{g.aScore}–{g.hScore}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DashboardScreen({ teamCols }) {
  return (
    <>
      <h1 className="large-title">Dashboard</h1>
      <p className="large-subtitle">Sunday, December 8 · Week 14</p>

      <div className="dashboard-grid">
        <div>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
            <div className="section-label" style={{ color: "var(--move)", margin: 0 }}>Scoring</div>
            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
              {TEAMS.length} teams · {TEAMS.filter(t => t.live).length} live
            </span>
          </div>
          <div className="team-grid" style={{ "--team-cols": teamCols }}>
            {TEAMS.map(t => <TeamCard key={t.id} team={t} />)}
          </div>
        </div>

        <div className="rail">
          <div className="section-label" style={{ margin: 0 }}>Insights</div>
          <InsightTopPerformer />
          <InsightWeeklyTrend />
          <InsightLiveGames />
        </div>
      </div>
    </>
  );
}

Object.assign(window, { DashboardScreen });
