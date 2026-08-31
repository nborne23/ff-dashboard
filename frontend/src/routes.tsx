import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import { DRAFT_ASSISTANT } from "./features";
import Dashboard from "./screens/Dashboard";
import Draft from "./screens/Draft";
import GameDay from "./screens/GameDay";
import HeadToHead from "./screens/HeadToHead";
import MyTeam from "./screens/MyTeam";
import Season from "./screens/Season";
import Settings from "./screens/Settings";
import Waivers from "./screens/Waivers";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "gameday", element: <GameDay /> },
      { path: "team/:teamId", element: <MyTeam /> },
      { path: "team/:teamId/h2h", element: <HeadToHead /> },
      { path: "team/:teamId/season", element: <Season /> },
      { path: "team/:teamId/waivers", element: <Waivers /> },
      ...(DRAFT_ASSISTANT ? [{ path: "draft", element: <Draft /> }] : []),
      { path: "settings", element: <Settings /> },
    ],
  },
]);
