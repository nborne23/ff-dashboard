// The desktop sidebar: Game Day, every team by name, Settings. Nothing else.
//
// It used to carry Matchups / Season / Waivers / League as top-level links. Those are
// views OF a team, so they had to resolve to some team. They silently picked whichever
// one you had looked at last, and they duplicated the tabs on the team page. Now the
// sidebar answers "where" (which team) and the team page's tabs answer "what" (which
// view). Each axis has exactly one control.
//
// Every team is listed directly, with its current margin, so the sidebar doubles as a
// six-line scoreboard on screens other than Game Day.

import { Link, NavLink, useLocation } from "react-router-dom";

import { TeamLogo } from "../shared/TeamLogo";

import { useTeams } from "../../api/teams";
import { DRAFT_ASSISTANT } from "../../features";
import { parseTeamRoute, teamRoutePath } from "../../hooks/teamRoute";
import { useUiStore } from "../../stores/ui";
import type { Team } from "../../types/api";
import { IconBolt, IconChevR, IconFlame, IconFootball, IconSettings } from "../primitives";

function navItemClassName({ isActive }: { isActive: boolean }): string {
  return "nav-item" + (isActive ? " active" : "");
}

/** Margin for the sidebar's scoreboard column. Blank before kickoff: 0.0 vs 0.0 is not
 *  a tie worth showing in six rows. */
function teamMargin(team: Team): { text: string; sign: "pos" | "neg" | "even" } | null {
  if (team.current_score === 0 && team.current_opp_score === 0) return null;
  const margin = team.current_score - team.current_opp_score;
  if (Math.abs(margin) < 0.05) return { text: "Even", sign: "even" };
  return {
    text: `${margin > 0 ? "+" : "−"}${Math.abs(margin).toFixed(1)}`,
    sign: margin > 0 ? "pos" : "neg",
  };
}

export function Sidebar() {
  const location = useLocation();
  const week = useUiStore((s) => s.week);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const teamsQuery = useTeams(week);

  const teams = teamsQuery.data?.data.teams ?? [];
  const teamRoute = parseTeamRoute(location.pathname);
  // Moving between teams keeps the view: from one team's Season, another team's row
  // goes to that team's Season. Off a team page, rows open the roster.
  const section = teamRoute?.section ?? "roster";

  return (
    <aside className="sidebar" aria-label="Primary">
      <div className="brand">
        <span className="logo" aria-hidden="true">
          <IconFootball size={22} color="var(--accent)" />
        </span>
        <span className="name">GridIron</span>
        {/* Collapsing hands ~180px back to the content column, which on Game Day goes
            straight into panel width. */}
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

      <nav className="nav-group">
        <NavLink to="/" end className={navItemClassName} title="Game Day">
          <span className="icon">
            <IconBolt size={18} />
          </span>
          <span className="label">Game Day</span>
        </NavLink>
        {DRAFT_ASSISTANT && (
          <NavLink to="/draft" className={navItemClassName} title="Draft">
            <span className="icon">
              <IconFlame size={18} />
            </span>
            <span className="label">Draft</span>
          </NavLink>
        )}
      </nav>

      <nav className="nav-group nav-teams" aria-label="Teams">
        <div className="nav-label">Teams</div>
        {teams.map((t) => {
          const isActive = teamRoute?.teamId === t.id;
          const margin = teamMargin(t);
          return (
            <Link
              key={t.id}
              to={teamRoutePath(t.id, section)}
              className={"team-item" + (isActive ? " active" : "")}
              aria-current={isActive ? "page" : undefined}
              title={t.name}
            >
              <span className="team-item-logo">
                <TeamLogo team={t} size={28} />
                {t.is_live && <span className="team-item-live" aria-label="Live" />}
              </span>
              <span className="label">{t.name}</span>
              {margin && (
                <span className="team-item-margin" data-sign={margin.sign}>
                  {margin.text}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <nav className="nav-group nav-footer">
        <NavLink to="/settings" className={navItemClassName} title="Settings">
          <span className="icon">
            <IconSettings size={18} />
          </span>
          <span className="label">Settings</span>
        </NavLink>
      </nav>
    </aside>
  );
}
