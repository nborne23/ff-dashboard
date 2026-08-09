import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import Dashboard from "./screens/Dashboard";
import HeadToHead from "./screens/HeadToHead";
import MyTeam from "./screens/MyTeam";
import Season from "./screens/Season";
import Settings from "./screens/Settings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "team/:teamId", element: <MyTeam /> },
      { path: "team/:teamId/h2h", element: <HeadToHead /> },
      { path: "team/:teamId/season", element: <Season /> },
      { path: "settings", element: <Settings /> },
    ],
  },
]);
