// Main GridIron app — orchestrates screens, navigation, tweaks.

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "sidebarWidth": 240,
  "teamCols": 2,
  "rowHeight": 56,
  "showInsights": true,
  "sparkThickness": 1.5,
  "auroraIntensity": 0.18,
  "currentScreen": "dashboard"
}/*EDITMODE-END*/;

const SCREEN_AURORAS = {
  "dashboard": "rgba(255, 45, 85, ALPHA)",
  "myteam":    "rgba(255, 45, 85, ALPHA)",
  "h2h":       "rgba(191, 90, 242, ALPHA)",
  "season":    "rgba(100, 210, 255, ALPHA)",
  "settings":  "rgba(142, 142, 147, ALPHA)",
};

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [active, setActive] = React.useState(tweaks.currentScreen || "dashboard");
  const [teamsExpanded, setTeamsExpanded] = React.useState(false);
  const [week, setWeek] = React.useState(14);

  // Apply CSS variables from tweaks
  React.useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--sidebar-w", tweaks.sidebarWidth + "px");
    root.style.setProperty("--row-h", tweaks.rowHeight + "px");
    root.style.setProperty("--spark-thick", tweaks.sparkThickness + "px");
  }, [tweaks.sidebarWidth, tweaks.rowHeight, tweaks.sparkThickness]);

  const handleNav = (id) => {
    if (id.startsWith("team-")) {
      setActive("myteam");
    } else {
      setActive(id);
    }
  };

  const screenKey = active === "myteam" || active.startsWith("team-") ? "myteam" : active;
  const auroraColor = (SCREEN_AURORAS[screenKey] || SCREEN_AURORAS.dashboard)
    .replace("ALPHA", tweaks.auroraIntensity.toString());

  const renderScreen = () => {
    switch (screenKey) {
      case "dashboard": return <DashboardScreen teamCols={tweaks.teamCols} />;
      case "myteam":    return <MyTeamScreen />;
      case "matchups":  return <H2HScreen />;
      case "h2h":       return <H2HScreen />;
      case "season":    return <SeasonScreen />;
      case "settings":  return <SettingsScreen />;
      default:          return <DashboardScreen teamCols={tweaks.teamCols} />;
    }
  };

  // Show insights collapsed override via CSS class
  React.useEffect(() => {
    const styleId = "__insights-toggle";
    let s = document.getElementById(styleId);
    if (!s) {
      s = document.createElement("style");
      s.id = styleId;
      document.head.appendChild(s);
    }
    s.textContent = tweaks.showInsights
      ? ""
      : `.dashboard-grid { grid-template-columns: 1fr !important; } .dashboard-grid .rail { display: none !important; }`;
  }, [tweaks.showInsights]);

  return (
    <div className="app">
      <Sidebar
        active={active.startsWith("team-") ? active : (active === "myteam" ? "team-yhb" : active)}
        onNav={handleNav}
        expanded={teamsExpanded}
        onToggleTeams={() => setTeamsExpanded(!teamsExpanded)}
      />
      <div className="main">
        <Aurora color={auroraColor} />
        <Topbar week={week} onWeekChange={setWeek} />
        <div className="content">
          <div className="content-inner">
            {renderScreen()}
          </div>
        </div>
      </div>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Navigation">
          <TweakSelect
            label="Current screen"
            value={active}
            options={[
              { value: "dashboard", label: "Dashboard" },
              { value: "myteam",    label: "My Team" },
              { value: "h2h",       label: "Head-to-Head" },
              { value: "season",    label: "Season" },
              { value: "settings",  label: "Settings" },
            ]}
            onChange={(v) => { setActive(v); setTweak("currentScreen", v); }}
          />
        </TweakSection>

        <TweakSection label="Layout">
          <TweakSlider
            label="Sidebar width"
            value={tweaks.sidebarWidth}
            min={200} max={280} step={4} unit="px"
            onChange={(v) => setTweak("sidebarWidth", v)}
          />
          <TweakRadio
            label="Team cards / row"
            value={tweaks.teamCols}
            options={[{ value: 2, label: "2" }, { value: 3, label: "3" }]}
            onChange={(v) => setTweak("teamCols", v)}
          />
          <TweakSlider
            label="Roster row height"
            value={tweaks.rowHeight}
            min={48} max={72} step={2} unit="px"
            onChange={(v) => setTweak("rowHeight", v)}
          />
          <TweakToggle
            label="Show Insights rail"
            value={tweaks.showInsights}
            onChange={(v) => setTweak("showInsights", v)}
          />
        </TweakSection>

        <TweakSection label="Visuals">
          <TweakSlider
            label="Sparkline thickness"
            value={tweaks.sparkThickness}
            min={1} max={3} step={0.25} unit="px"
            onChange={(v) => setTweak("sparkThickness", v)}
          />
          <TweakSlider
            label="Aurora intensity"
            value={tweaks.auroraIntensity}
            min={0} max={0.4} step={0.02}
            onChange={(v) => setTweak("auroraIntensity", v)}
          />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
