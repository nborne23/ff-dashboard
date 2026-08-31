// The bar that makes team scope visible.
//
// Before this existed, "which team am I looking at?" was answerable only by reading the
// URL, and moving between a team's three views (Roster / Matchup / Season) meant going
// back out to the sidebar — where Matchups and Season pointed at an arbitrary team
// anyway. This renders only on `/team/:teamId/...` routes and does two things: names
// the team on screen (with a switcher), and offers its sibling views as tabs. Switching
// teams preserves the section, so comparing two teams' matchups is one click, not three.

import { TeamLogo } from "../shared/TeamLogo";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useTeams } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import { TEAM_SECTIONS, teamRoutePath, type TeamSection } from "../../hooks/teamRoute";
import { IconChevR } from "../primitives";

interface TeamContextBarProps {
  teamId: string;
  section: TeamSection;
}

export function TeamContextBar({ teamId, section }: TeamContextBarProps) {
  const navigate = useNavigate();
  const week = useUiStore((s) => s.week);
  const teamsQuery = useTeams(week);
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const teams = teamsQuery.data?.data.teams ?? [];
  const current = teams.find((t) => t.id === teamId);

  // Close on an outside click or Escape. Bound only while open so the listeners aren't
  // live on every screen for a menu nobody has opened.
  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  // A team id from the URL that isn't in the list yet (still loading, or a stale link)
  // still gets a label rather than an empty button.
  const label = current?.name ?? "Select a team";

  return (
    <div className="team-context" data-testid="team-context" ref={rootRef}>
      <div className="team-switcher">
        <button
          type="button"
          className="team-switcher-btn"
          aria-haspopup="listbox"
          aria-expanded={menuOpen}
          disabled={teams.length === 0}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {current && (
            <span
              className="platform-dot"
              style={{
                background: current.id.startsWith("yahoo") ? "var(--yahoo)" : "var(--espn)",
              }}
            />
          )}
          <span className="team-switcher-name">{label}</span>
          <span className={"chev" + (menuOpen ? " open" : "")}>
            <IconChevR size={12} />
          </span>
        </button>
        {menuOpen && (
          <ul className="team-switcher-menu" role="listbox" aria-label="Switch team">
            {teams.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={t.id === teamId}
                  className={"team-switcher-option" + (t.id === teamId ? " active" : "")}
                  onClick={() => {
                    setMenuOpen(false);
                    // Keep the section: switching teams from the Season view lands on
                    // the other team's Season view, not back at its roster.
                    navigate(teamRoutePath(t.id, section));
                  }}
                >
                  <TeamLogo team={t} size={18} />
                  <span className="team-switcher-name">{t.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <nav className="team-tabs" aria-label="Team views">
        {TEAM_SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={"team-tab" + (s.id === section ? " active" : "")}
            aria-current={s.id === section ? "page" : undefined}
            onClick={() => navigate(teamRoutePath(teamId, s.id))}
          >
            {s.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
