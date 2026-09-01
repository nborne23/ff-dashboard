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

/**
 * Smallest size a team avatar may render at.
 *
 * Not a style preference — a legibility floor grounded in the real data. 43% of the
 * avatars in these leagues are `CUSTOM_UPLOAD`: photographs a leaguemate uploaded,
 * including group shots and a 315KB PNG. Rendered at 14–18px those are coloured
 * smudges, indistinguishable from one another, so an avatar below this size is not
 * an identity cue — it is noise occupying the space where the team name should be.
 *
 * ESPN's own `VECTOR` crests survive smaller, but splitting the floor by type would
 * give a team two identities (a photo in standings, initials in the sidebar) and
 * defeat the point of an avatar, which is recognition at a glance.
 */
export const LOGO_MIN_SIZE = 24;

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
  /** Rendered size in px. Values below `LOGO_MIN_SIZE` are clamped up to it. */
  size?: number;
  /** Optional platform accent drawn as a ring around the logo.
   *
   *  This is how the Dashboard card keeps the information its platform pill used to
   *  carry. That pill cost 46px in a 127px row, which left too little for the team
   *  name — a ring costs no horizontal space at all. Uses `box-shadow` rather than
   *  `border` so it does not shrink the image's content box or shift the row. */
  ringColor?: string;
}

export function TeamLogo({ team, size = LOGO_MIN_SIZE, ringColor }: TeamLogoProps) {
  const [failed, setFailed] = useState(false);

  // Clamped rather than trusted: the floor is the whole point, and a call site that
  // passes 14 to fit a tight row would silently reintroduce the illegible case.
  const px = Math.max(size, LOGO_MIN_SIZE);

  const box = {
    width: px,
    height: px,
    borderRadius: 6,
    flex: "0 0 auto",
    ...(ringColor ? { boxShadow: `0 0 0 1.5px ${ringColor}` } : {}),
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
          fontSize: Math.max(9, Math.round(px * 0.4)),
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
