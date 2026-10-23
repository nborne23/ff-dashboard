import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import { DRAFT_ASSISTANT } from "./features";
import Draft from "./screens/Draft";
import GameDay from "./screens/GameDay";
import GameDayRedirect from "./screens/GameDay/GameDayRedirect";
import LeagueScreen from "./screens/League";
import LeagueTeam from "./screens/League/LeagueTeam";
import HeadToHead from "./screens/HeadToHead";
import MyTeam from "./screens/MyTeam";
import Season from "./screens/Season";
import Settings from "./screens/Settings";
import Waivers from "./screens/Waivers";

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
  ...(DRAFT_ASSISTANT ? [{ path: "draft", element: <Draft /> }] : []),
  { path: "settings", element: <Settings /> },
];

export const router = createBrowserRouter([
  { path: "/", element: <App />, children: routeChildren },
]);
