// One team logo, used everywhere a team is named: standings, Dashboard cards, the
// sidebar list, the team switcher, and the matchup panels.
//
// Two fallback paths, and they are not the same:
//
//   - `logo_url` is null (the team has no logo upstream). Render the placeholder and
//     issue NO request — the backend would only answer with a crest we can draw here.
//   - `logo_url` is present but the image fails to load. Fall back on `onError`, the
//     same pattern `RosterTable`'s `Headshot` already uses for missing headshots.

import { useState } from "react";

import type { Team } from "../../types/api";

function initialsFor(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export interface TeamLogoProps {
  team: Pick<Team, "name" | "logo_url">;
  size?: number;
}

export function TeamLogo({ team, size = 24 }: TeamLogoProps) {
  const [failed, setFailed] = useState(false);

  const box = {
    width: size,
    height: size,
    borderRadius: size <= 20 ? 4 : 6,
    flex: "0 0 auto",
  } as const;

  if (!team.logo_url || failed) {
    return (
      <div
        className="team-logo team-logo-fallback"
        style={{
          ...box,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--card-2, #2A2A2E)",
          color: "var(--text-secondary)",
          fontSize: Math.max(9, Math.round(size * 0.4)),
          fontWeight: 700,
          letterSpacing: "0.02em",
        }}
        aria-hidden="true"
        data-testid="team-logo-fallback"
      >
        {initialsFor(team.name)}
      </div>
    );
  }

  return (
    <img
      className="team-logo"
      src={team.logo_url}
      alt=""
      aria-hidden="true"
      onError={() => setFailed(true)}
      style={{ ...box, objectFit: "cover", background: "var(--card-2, #2A2A2E)" }}
    />
  );
}
