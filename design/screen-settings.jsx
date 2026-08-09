// Screen 5: Settings

function Switch({ on, onChange }) {
  return <div className={"switch" + (on ? " on" : "")} onClick={() => onChange(!on)} />;
}

function SettingsRow({ label, sub, right, last, onClick }) {
  return (
    <div className="row" style={last ? { borderBottom: "none" } : null} onClick={onClick}>
      <div className="label">
        <div>{label}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <div>{right}</div>
    </div>
  );
}

function SettingsScreen() {
  const [yahoo, setYahoo] = React.useState(true);
  const [espn, setEspn] = React.useState(true);
  const [leagues, setLeagues] = React.useState({ office: true, family: true, money: false });
  const [polling, setPolling] = React.useState("Every 30s");
  const [notifs, setNotifs] = React.useState({ scoreChange: true, redzone: true, finalScore: true });

  return (
    <>
      <h1 className="large-title" style={{ textAlign: "left" }}>Settings</h1>
      <p className="large-subtitle">Account, leagues, and preferences</p>

      <div className="settings-page">
        <h3>Connected Platforms</h3>
        <div className="settings-group">
          <SettingsRow
            label={
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="pill yahoo">YAHOO</span>
                <span>Yahoo Fantasy</span>
              </span>
            }
            sub="Connected as gritty.linebacker · 4 leagues found"
            right={<Switch on={yahoo} onChange={setYahoo} />}
          />
          <SettingsRow
            label={
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="pill espn">ESPN</span>
                <span>ESPN Fantasy</span>
              </span>
            }
            sub="Connected as 8tracksandahuddle · 3 leagues found"
            right={<Switch on={espn} onChange={setEspn} />}
            last
          />
        </div>
        <div style={{ padding: "0 16px", marginTop: -16, marginBottom: 24, fontSize: 12, color: "var(--text-secondary)" }}>
          Leagues sync every 30 seconds during live games and every 10 minutes otherwise.
        </div>

        <h3>ESPN Leagues</h3>
        <div className="settings-group">
          <SettingsRow
            label="Office League"
            sub="ESPN · 10 teams · standard scoring"
            right={<Switch on={leagues.office} onChange={v => setLeagues({...leagues, office: v})} />}
          />
          <SettingsRow
            label="Friday Night Lights"
            sub="ESPN · 14 teams · half PPR"
            right={<Switch on={true} onChange={() => {}} />}
          />
          <SettingsRow
            label="Money League"
            sub="ESPN · 10 teams · full PPR · superflex"
            right={<Switch on={leagues.money} onChange={v => setLeagues({...leagues, money: v})} />}
            last
          />
        </div>

        <h3>ESPN Credentials</h3>
        <div className="settings-group">
          <div className="field-row" style={{ borderBottom: "0.5px solid var(--separator)" }}>
            <div className="label">SWID</div>
            <input type="text" placeholder="{xxxx-xxxx-xxxx}" defaultValue="{A1B2C3D4-E5F6-…}" />
          </div>
          <div className="field-row" style={{ borderBottom: "0.5px solid var(--separator)" }}>
            <div className="label">espn_s2</div>
            <input type="password" defaultValue="••••••••••••••••••••" />
          </div>
          <SettingsRow
            label={<span style={{ color: "var(--text-secondary)", fontSize: 13 }}>Last verified 4 minutes ago</span>}
            right={<button className="btn">Test Connection</button>}
            last
          />
        </div>

        <h3>Preferences</h3>
        <div className="settings-group">
          <SettingsRow
            label="Polling frequency"
            sub="How often to refresh during live games"
            right={
              <div className="segmented">
                {["10s", "30s", "1m"].map(v => (
                  <button key={v} className={polling.includes(v) ? "active" : ""} onClick={() => setPolling(`Every ${v}`)}>{v}</button>
                ))}
              </div>
            }
          />
          <SettingsRow
            label="Notify on score change"
            sub="Push when a starter scores 6+ pts"
            right={<Switch on={notifs.scoreChange} onChange={v => setNotifs({...notifs, scoreChange: v})} />}
          />
          <SettingsRow
            label="Red zone alerts"
            sub="When my players enter the red zone"
            right={<Switch on={notifs.redzone} onChange={v => setNotifs({...notifs, redzone: v})} />}
          />
          <SettingsRow
            label="Final score recap"
            right={<Switch on={notifs.finalScore} onChange={v => setNotifs({...notifs, finalScore: v})} />}
            last
          />
        </div>

        <h3>Appearance</h3>
        <div className="settings-group">
          <SettingsRow
            label="Theme"
            right={
              <div className="segmented">
                <button className="active">Dark</button>
                <button>Light</button>
                <button>Auto</button>
              </div>
            }
          />
          <SettingsRow
            label="Accent color"
            right={
              <div style={{ display: "flex", gap: 8 }}>
                {["#FF2D55", "#30D158", "#64D2FF", "#FF9F0A", "#BF5AF2"].map((c, i) => (
                  <span key={c} style={{
                    width: 22, height: 22, borderRadius: "50%", background: c,
                    border: i === 0 ? "2px solid #fff" : "2px solid transparent",
                    cursor: "pointer",
                  }} />
                ))}
              </div>
            }
            last
          />
        </div>

        <h3>Data Management</h3>
        <div className="settings-group">
          <SettingsRow
            label="Refresh all data"
            sub="Force a full re-sync from connected platforms"
            right={<button className="btn">Refresh</button>}
          />
          <SettingsRow
            label="Clear cache"
            sub="14.2 MB stored locally"
            right={<button className="btn">Clear</button>}
          />
          <SettingsRow
            label="Export data"
            sub="Download teams, rosters, scoring as JSON"
            right={<button className="btn">Export JSON</button>}
          />
          <SettingsRow
            label={<span style={{ color: "var(--espn)" }}>Disconnect all platforms</span>}
            right={<button className="btn danger">Disconnect</button>}
            last
          />
        </div>

        <div style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: 11, padding: "12px 0 32px" }}>
          GridIron 1.0 · Build 2026.05.02
        </div>
      </div>
    </>
  );
}

Object.assign(window, { SettingsScreen });
