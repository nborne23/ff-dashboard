// Phone navigation: a bottom tab bar, replacing the hamburger drawer.
//
// The app has three destinations, so all three can be on screen at all times. A drawer
// hid them behind a tap and covered the screen to show them. "Teams" opens the team you
// were last following; the team page's own switcher moves between teams.

import { Link, NavLink, useLocation } from "react-router-dom";

import { useTeams } from "../../api/teams";
import { parseTeamRoute, resolveTeamId, teamRoutePath } from "../../hooks/teamRoute";
import { useUiStore } from "../../stores/ui";
import { IconBolt, IconSettings, IconTeams } from "../primitives";

export function TabBar() {
  const location = useLocation();
  const week = useUiStore((s) => s.week);
  const activeTeamId = useUiStore((s) => s.activeTeamId);
  const teamsQuery = useTeams(week);
  const teams = teamsQuery.data?.data.teams ?? [];
  const teamId = resolveTeamId(activeTeamId, teams);
  const onTeamRoute = parseTeamRoute(location.pathname) !== null;

  return (
    <nav className="tabbar" aria-label="Primary">
      <NavLink to="/" end className={({ isActive }) => "tab" + (isActive ? " active" : "")}>
        <IconBolt size={22} />
        <span>Game Day</span>
      </NavLink>
      {/* A plain Link: "current" means any team route, which NavLink's own matching
          against this one URL can't express. */}
      <Link
        to={teamId ? teamRoutePath(teamId, "roster") : "/settings"}
        className={"tab" + (onTeamRoute ? " active" : "")}
        aria-current={onTeamRoute ? "page" : undefined}
      >
        <IconTeams size={22} />
        <span>Teams</span>
      </Link>
      <NavLink to="/settings" className={({ isActive }) => "tab" + (isActive ? " active" : "")}>
        <IconSettings size={22} />
        <span>Settings</span>
      </NavLink>
    </nav>
  );
}
