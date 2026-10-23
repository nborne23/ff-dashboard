// The team header on `/team/:teamId/...`: which team this is, and which of its views
// you are on.
//
// It is the ONLY control for a team's views. The sidebar used to repeat them as
// top-level links. The switcher keeps the section, so comparing two teams' Season
// views is one tap. It opens as a popover anchored to its button and grows out of it
// (§7), rather than appearing from nowhere.

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

  // Close on an outside press or Escape. Bound only while open.
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

  // A team id from the URL that isn't in the list yet still gets a label.
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
          {current && <TeamLogo team={current} size={28} />}
          <span className="team-switcher-name">{label}</span>
          <span className={"chev" + (menuOpen ? " open" : "")} aria-hidden="true">
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
                    navigate(teamRoutePath(t.id, section));
                  }}
                >
                  <TeamLogo team={t} size={28} />
                  <span className="team-switcher-name">{t.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <nav className="team-tabs segmented" aria-label="Team views">
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
