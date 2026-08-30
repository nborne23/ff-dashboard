// Ported from design/shell.jsx's Sidebar. The prototype drove navigation via
// an `onNav(id)` callback into local App state; here NavLink/useNavigate own
// routing and "active" comes straight from the current URL.

import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useTeams } from "../../api/teams";
import { DRAFT_ASSISTANT } from "../../features";
import { useFreshness } from "../../hooks/useFreshness";
import { parseTeamRoute, resolveTeamId, teamRoutePath } from "../../hooks/teamRoute";
import { useLiveConnectionStore } from "../../stores/live";
import { useUiStore } from "../../stores/ui";
import {
  IconBolt,
  IconChevR,
  IconDashboard,
  IconFlame,
  IconFootball,
  IconMatchups,
  IconSeason,
  IconSettings,
  IconTeams,
} from "../primitives";

function navItemClassName({ isActive }: { isActive: boolean }): string {
  return "nav-item" + (isActive ? " active" : "");
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [teamsExpanded, setTeamsExpanded] = useState(false);
  const week = useUiStore((s) => s.week);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const activeTeamId = useUiStore((s) => s.activeTeamId);
  const teamsQuery = useTeams(week);
  const freshness = useFreshness(teamsQuery.data?.meta?.as_of);
  const connectionLostLong = useLiveConnectionStore((s) => s.connectionLostLong);

  const teams = teamsQuery.data?.data.teams ?? [];
  // Matchups/Season link to the team the user was last looking at — not to whichever
  // team happens to sort first, which is what made those two screens feel unrelated to
  // the team you had just opened. `resolveTeamId` falls back to the first team when the
  // remembered one is gone, and to `undefined` when nothing is connected at all, in
  // which case these links point at the dashboard and its "connect a league" state.
  const selectedTeamId = resolveTeamId(activeTeamId, teams);

  const teamRoute = parseTeamRoute(location.pathname);
  const onTeamRoute = teamRoute !== null;

  // Open the team list on ARRIVAL at a team screen, so the sidebar reflects where you
  // are instead of hiding the list you just navigated through.
  //
  // Two shapes were rejected before this one. A derived `teamsExpanded || onTeamRoute`
  // makes the toggle button inert while a team screen is open — it can never win
  // against the OR. An effect calling `setTeamsExpanded` is the cascading-render
  // pattern the lint rules reject. This is React's documented adjust-state-during-
  // render form: track the last value of the condition, and act only on the edge, so
  // entering a team route opens the list and a manual collapse while already on one
  // sticks.
  const [wasOnTeamRoute, setWasOnTeamRoute] = useState(false);
  if (onTeamRoute !== wasOnTeamRoute) {
    setWasOnTeamRoute(onTeamRoute);
    if (onTeamRoute) setTeamsExpanded(true);
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="logo">
          <IconFootball size={24} color="var(--move)" />
        </span>
        <span className="name">GridIron</span>
        {/* Collapsing to icons hands ~184px back to the content column — the reason it
            exists is Game Day, where that width goes straight into panel density. */}
        <button
          type="button"
          className="sidebar-toggle"
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!sidebarCollapsed}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <IconChevR size={12} />
        </button>
      </div>

      <div className="nav-group">
        <NavLink to="/" end className={navItemClassName}>
          <span className="icon">
            <IconDashboard size={18} />
          </span>
          <span className="label">Dashboard</span>
        </NavLink>

        {/* Between Dashboard and the "My Teams" group, and — unlike Matchups and
            Season below — a DIRECT link rather than a primaryTeamId one: Game Day
            spans every team, so there is no team to select. */}
        <NavLink to="/gameday" className={navItemClassName}>
          <span className="icon">
            <IconBolt size={18} />
          </span>
          <span className="label">Game Day</span>
        </NavLink>

        <button
          type="button"
          className={"nav-item" + (onTeamRoute ? " active" : "")}
          onClick={() => setTeamsExpanded((v) => !v)}
        >
          <span className="icon">
            <IconTeams size={18} />
          </span>
          <span className="label">My Teams</span>
          <span className={"chev" + (teamsExpanded ? " open" : "")}>
            <IconChevR size={12} />
          </span>
        </button>
        {teamsExpanded &&
          teams.map((t) => {
            const platform = t.id.split(":")[0];
            const teamPath = teamRoutePath(t.id, "roster");
            // Highlight the team while ANY of its three views is on screen, not just
            // its roster — the section is shown by the TeamContextBar's tabs.
            const isActive = teamRoute?.teamId === t.id;
            return (
              <button
                key={t.id}
                type="button"
                className={"sub-item" + (isActive ? " active" : "")}
                onClick={() => navigate(teamPath)}
              >
                <span
                  className="platform-dot"
                  style={{ background: platform === "yahoo" ? "var(--yahoo)" : "var(--espn)" }}
                />
                <span
                  style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {t.name}
                </span>
              </button>
            );
          })}

        <NavLink
          to={selectedTeamId ? teamRoutePath(selectedTeamId, "h2h") : "/"}
          className={navItemClassName}
        >
          <span className="icon">
            <IconMatchups size={18} />
          </span>
          <span className="label">Matchups</span>
        </NavLink>
        <NavLink
          to={selectedTeamId ? teamRoutePath(selectedTeamId, "season") : "/"}
          className={navItemClassName}
        >
          <span className="icon">
            <IconSeason size={18} />
          </span>
          <span className="label">Season</span>
        </NavLink>
        {DRAFT_ASSISTANT && (
          <NavLink to="/draft" className={navItemClassName}>
            <span className="icon">
              <IconFlame size={18} />
            </span>
            <span className="label">Draft</span>
          </NavLink>
        )}
      </div>

      <div className="nav-group">
        <NavLink to="/settings" className={navItemClassName}>
          <span className="icon">
            <IconSettings size={18} />
          </span>
          <span className="label">Settings</span>
        </NavLink>
      </div>

      <div className="footer">
        <span className={"pulse" + (connectionLostLong ? " lost" : "")} />
        <span className="label">
          {connectionLostLong ? "Live connection lost — retrying" : freshness.label}
        </span>
      </div>
    </aside>
  );
}
