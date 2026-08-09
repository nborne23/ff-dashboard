// Shell — Sidebar, Topbar, Aurora.

function Sidebar({ active, onNav, expanded, onToggleTeams }) {
  const items = [
    { id: "dashboard", label: "Dashboard", Icon: IconDashboard },
    { id: "teams",     label: "My Teams",  Icon: IconTeams, expandable: true },
    { id: "matchups",  label: "Matchups",  Icon: IconMatchups },
    { id: "season",    label: "Season",    Icon: IconSeason },
  ];
  const settings = [
    { id: "settings", label: "Settings", Icon: IconSettings },
  ];

  const renderItem = (it) => {
    const isActive = active === it.id || (it.id === "teams" && active.startsWith("team-"));
    return (
      <React.Fragment key={it.id}>
        <button
          className={"nav-item" + (isActive ? " active" : "")}
          onClick={() => {
            if (it.expandable) onToggleTeams();
            else onNav(it.id);
          }}>
          <span className="icon"><it.Icon size={18} /></span>
          <span className="label">{it.label}</span>
          {it.expandable && (
            <span className={"chev" + (expanded ? " open" : "")}>
              <IconChevR size={12} />
            </span>
          )}
        </button>
        {it.expandable && expanded && TEAMS.map(t => (
          <button key={t.id}
            className={"sub-item" + (active === `team-${t.id}` ? " active" : "")}
            onClick={() => onNav(`team-${t.id}`)}>
            <span className="platform-dot" style={{ background: t.platform === "yahoo" ? "var(--yahoo)" : "var(--espn)" }} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</span>
          </button>
        ))}
      </React.Fragment>
    );
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="logo"><IconFootball size={24} color="var(--move)" /></span>
        <span className="name">GridIron</span>
      </div>
      <div className="nav-group">
        {items.map(renderItem)}
      </div>
      <div className="nav-group">
        {settings.map(renderItem)}
      </div>
      <div className="footer">
        <span className="pulse" />
        <span className="label">Last updated 12s ago</span>
      </div>
    </aside>
  );
}

function Topbar({ week, onWeekChange }) {
  return (
    <header className="topbar">
      <div className="week-nav">
        <button className="icon-btn" onClick={() => onWeekChange(week - 1)} aria-label="Previous week">
          <IconArrowL size={16} />
        </button>
        <span className="week-label">Week {week}</span>
        <button className="icon-btn" onClick={() => onWeekChange(week + 1)} aria-label="Next week">
          <IconArrowR size={16} />
        </button>
      </div>
      <DayRings days={WEEK_DAYS} today={3} />
      <div className="right-cluster">
        <span className="live-badge">
          <span className="dot" />
          3 LIVE
        </span>
        <button className="icon-btn" aria-label="Refresh"><IconRefresh size={16} /></button>
      </div>
    </header>
  );
}

function Aurora({ color = "rgba(255, 45, 85, 0.18)" }) {
  return <div className="aurora" style={{ "--aurora-color": color }} />;
}

Object.assign(window, { Sidebar, Topbar, Aurora });
