// Ported from design/shell.jsx's Sidebar. The prototype drove navigation via
// an `onNav(id)` callback into local App state; here NavLink/useNavigate own
// routing and "active" comes straight from the current URL.

import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useTeams } from "../../api/teams";
import { useFreshness } from "../../hooks/useFreshness";
import { useLiveConnectionStore } from "../../stores/live";
import { useUiStore } from "../../stores/ui";
import {
  IconChevR,
  IconDashboard,
  IconFootball,
  IconMatchups,
  IconSeason,
  IconSettings,
  IconTeams,
} from "../primitives";
import { PLACEHOLDER_TEAMS } from "./placeholderShellData";

// PLACEHOLDER: Matchups/Season need *a* team to link to before there's a
// notion of a "selected" team (that lands with real data in Phase 4/5) — use
// the first placeholder team as a stand-in.
const PRIMARY_TEAM_ID = PLACEHOLDER_TEAMS[0].id;

function navItemClassName({ isActive }: { isActive: boolean }): string {
  return "nav-item" + (isActive ? " active" : "");
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [teamsExpanded, setTeamsExpanded] = useState(false);
  const week = useUiStore((s) => s.week);
  const teamsQuery = useTeams(week);
  const freshness = useFreshness(teamsQuery.data?.meta?.as_of);
  const connectionLostLong = useLiveConnectionStore((s) => s.connectionLostLong);

  const isTeamRoute = location.pathname.startsWith("/team/");
  const isH2H = location.pathname.endsWith("/h2h");
  const isSeason = location.pathname.endsWith("/season");
  const isMyTeamActive = isTeamRoute && !isH2H && !isSeason;

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="logo">
          <IconFootball size={24} color="var(--move)" />
        </span>
        <span className="name">GridIron</span>
      </div>

      <div className="nav-group">
        <NavLink to="/" end className={navItemClassName}>
          <span className="icon">
            <IconDashboard size={18} />
          </span>
          <span className="label">Dashboard</span>
        </NavLink>

        <button
          type="button"
          className={"nav-item" + (isMyTeamActive ? " active" : "")}
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
          PLACEHOLDER_TEAMS.map((t) => {
            const teamPath = `/team/${t.id}`;
            const isActive = isMyTeamActive && location.pathname === teamPath;
            return (
              <button
                key={t.id}
                type="button"
                className={"sub-item" + (isActive ? " active" : "")}
                onClick={() => navigate(teamPath)}
              >
                <span
                  className="platform-dot"
                  style={{ background: t.platform === "yahoo" ? "var(--yahoo)" : "var(--espn)" }}
                />
                <span
                  style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {t.name}
                </span>
              </button>
            );
          })}

        <NavLink to={`/team/${PRIMARY_TEAM_ID}/h2h`} className={navItemClassName}>
          <span className="icon">
            <IconMatchups size={18} />
          </span>
          <span className="label">Matchups</span>
        </NavLink>
        <NavLink to={`/team/${PRIMARY_TEAM_ID}/season`} className={navItemClassName}>
          <span className="icon">
            <IconSeason size={18} />
          </span>
          <span className="label">Season</span>
        </NavLink>
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
