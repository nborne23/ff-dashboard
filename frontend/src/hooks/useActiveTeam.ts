// Keeps `ui.activeTeamId` in step with the URL.
//
// Deliberately write-only in one direction: the route writes the store, and nothing
// reads the store back to decide what renders. The three team screens keep reading
// `useParams().teamId`, so a pasted deep link, a back button, and a cold start with an
// empty store all behave identically. The store exists purely so that navigating to
// Matchups or Season from the shell lands on the team the user was already looking at.

import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { useUiStore } from "../stores/ui";
import { parseTeamRoute } from "./teamRoute";

export function useActiveTeamSync(): void {
  const pathname = useLocation().pathname;
  const setActiveTeamId = useUiStore((s) => s.setActiveTeamId);

  useEffect(() => {
    const match = parseTeamRoute(pathname);
    // Leaving a team route does NOT clear the memory — that's the whole point. The
    // user goes Dashboard -> Matchups and expects the team they last opened.
    if (match) setActiveTeamId(match.teamId);
  }, [pathname, setActiveTeamId]);
}
