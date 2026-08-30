// The three team-scoped screens — My Team, Matchups (Head-to-Head), and Season — are
// all `/team/:teamId/...` routes, so the URL is the single source of truth for which
// team is on screen. Everything here is pure so both the shell (Sidebar's links, the
// TeamContextBar's switcher and tabs) and the tests can share one parser instead of
// each re-deriving "is this the h2h route?" with its own `pathname.endsWith` check.

/** The three views a team has. `"roster"` is the bare `/team/:teamId` route. */
export type TeamSection = "roster" | "h2h" | "season";

export interface TeamRouteMatch {
  teamId: string;
  section: TeamSection;
}

/** Tab/section metadata, in the order they render. */
export const TEAM_SECTIONS: { id: TeamSection; label: string }[] = [
  { id: "roster", label: "Roster" },
  { id: "h2h", label: "Matchup" },
  { id: "season", label: "Season" },
];

/**
 * Parse a pathname into the team + section it addresses, or `null` when it is not a
 * team-scoped route at all (Dashboard, Game Day, Settings, ...).
 *
 * Returns `null` for an unrecognized sub-route (`/team/x/whatever`) rather than
 * guessing `"roster"`: that path renders nothing today, and reporting it as a valid
 * team route would light up a tab for a screen the user is not on.
 */
export function parseTeamRoute(pathname: string): TeamRouteMatch | null {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] !== "team" || !segments[1]) return null;

  // Team ids carry a colon (`espn:l-1234567-t-2`). Colons are legal in a path segment
  // and `navigate()` leaves them alone, but a hand-typed or copied URL may arrive
  // percent-encoded, and `useParams` would decode it — so decode here too, or the id
  // this returns would not match the one the screens actually render.
  let teamId = segments[1];
  try {
    teamId = decodeURIComponent(teamId);
  } catch {
    // Malformed escape sequence; fall through with the raw segment.
  }

  const tail = segments[2];
  if (tail === undefined) return { teamId, section: "roster" };
  if (tail === "h2h" || tail === "season") return { teamId, section: tail };
  return null;
}

/** Build the path for one team's section. Inverse of `parseTeamRoute`. */
export function teamRoutePath(teamId: string, section: TeamSection): string {
  return section === "roster" ? `/team/${teamId}` : `/team/${teamId}/${section}`;
}

/**
 * Pick which team the shell's team-scoped links should point at.
 *
 * The remembered team wins, but only after it is confirmed still present in the live
 * team list — a persisted id survives disconnecting that league, and an unvalidated
 * one would produce a sidebar link to an error screen that no reload could clear.
 * Falling back to the first team is a fallback, not a preference: `useTeams` ordering
 * is not a guarantee, which is exactly why the remembered id is checked first.
 */
export function resolveTeamId(
  activeTeamId: string | null,
  teams: { id: string }[],
): string | undefined {
  if (activeTeamId && teams.some((t) => t.id === activeTeamId)) return activeTeamId;
  return teams[0]?.id;
}
