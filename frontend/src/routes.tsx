import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import { DRAFT_ASSISTANT } from "./features";
import Draft from "./screens/Draft";
import GameDay from "./screens/GameDay";
import GameDayRedirect from "./screens/GameDay/GameDayRedirect";
import LeagueScreen from "./screens/League";
import LeagueTeam from "./screens/League/LeagueTeam";
import LeagueMatchups from "./screens/LeagueMatchups";
import MatchupDetail from "./screens/LeagueMatchups/MatchupDetail";
import HeadToHead from "./screens/HeadToHead";
import MyTeam from "./screens/MyTeam";
import Season from "./screens/Season";
import Settings from "./screens/Settings";
import Waivers from "./screens/Waivers";
import Scores from "./screens/Scores";
import ScoresGame from "./screens/Scores/GameDetail";

/** The shell's child routes, exported so tests can mount them in a memory router. */
export const routeChildren = [
  { index: true, element: <GameDay /> },
  // Both of these are retired URLs kept alive as redirects: "/gameday" from before Game
  // Day became the index route, and "/dashboard" from the screen that used to be the
  // landing page. A wall display restored from a bookmark or from session history must
  // not come back to a blank route.
  { path: "gameday", element: <GameDayRedirect /> },
  { path: "dashboard", element: <GameDayRedirect /> },
  { path: "team/:teamId", element: <MyTeam /> },
  { path: "team/:teamId/h2h", element: <HeadToHead /> },
  { path: "team/:teamId/season", element: <Season /> },
  { path: "team/:teamId/waivers", element: <Waivers /> },
  { path: "team/:teamId/league", element: <LeagueScreen /> },
  { path: "team/:teamId/league/:rosterTeamId", element: <LeagueTeam /> },
  // Static "matchups" outranks the dynamic `:rosterTeamId` above, and staying under
  // `league/` keeps the League tab selected (hooks/teamRoute.ts) with no parser change.
  { path: "team/:teamId/league/matchups", element: <LeagueMatchups /> },
  { path: "team/:teamId/league/matchups/:matchupId", element: <MatchupDetail /> },
  ...(DRAFT_ASSISTANT ? [{ path: "draft", element: <Draft /> }] : []),
  { path: "settings", element: <Settings /> },
  { path: "scores", element: <Scores /> },
  { path: "scores/game/:gameId", element: <ScoresGame /> },
];

export const router = createBrowserRouter([
  { path: "/", element: <App />, children: routeChildren },
]);
