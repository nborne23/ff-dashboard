// Where a team lives on its own platform, derived from the team's stable id alone.
//
// The ids already carry everything the platform URL needs (`espn:l-{league}-t-{team}`,
// `yahoo:{game}.l.{league}.t.{team}`), so this needs no API field and no extra request.
//
// Both URLs are https universal links, not custom URL schemes. Each host publishes an
// apple-app-site-association claiming these exact paths for its iOS app — ESPN's
// `/*/team` for ESPN Fantasy, Yahoo's `/f1/*/*` for Yahoo Fantasy — so on a phone with
// the app installed iOS opens the app straight on the team, and anywhere else the same
// URL is the platform's own website. A custom scheme would open the app too, but has no
// web fallback and neither app documents a scheme that lands on a specific team.
//
// Both point at the team, not the league: it is the more useful landing, and Yahoo's
// league page (`/f1/{league}`) is one path segment short of the pattern its app claims.

import type { Platform } from "../../types/api";

export interface SourceAppLink {
  platform: Platform;
  /** The platform's name as its app is known: "ESPN", "Yahoo". */
  label: string;
  url: string;
}

const ESPN_TEAM_ID = /^espn:l-(\d+)-t-(\d+)$/;
const YAHOO_TEAM_ID = /^yahoo:[^.]+\.l\.(\d+)\.t\.(\d+)$/;

/** The team's page on its source platform, or null for an id this can't place. */
export function sourceAppLink(teamId: string): SourceAppLink | null {
  const espn = ESPN_TEAM_ID.exec(teamId);
  if (espn) {
    const [, leagueId, team] = espn;
    // No seasonId: ESPN defaults to the current season, which is the only one this app
    // tracks, and leaving it out keeps a bookmark-style link valid across a rollover.
    return {
      platform: "espn",
      label: "ESPN",
      url: `https://fantasy.espn.com/football/team?leagueId=${leagueId}&teamId=${team}`,
    };
  }
  const yahoo = YAHOO_TEAM_ID.exec(teamId);
  if (yahoo) {
    const [, leagueId, team] = yahoo;
    return {
      platform: "yahoo",
      label: "Yahoo",
      url: `https://football.fantasysports.yahoo.com/f1/${leagueId}/${team}`,
    };
  }
  return null;
}
