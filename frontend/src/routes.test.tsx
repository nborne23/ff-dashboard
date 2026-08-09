import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import App from "./App";
import Dashboard from "./screens/Dashboard";
import HeadToHead from "./screens/HeadToHead";
import MyTeam from "./screens/MyTeam";
import Season from "./screens/Season";
import Settings from "./screens/Settings";

describe("routes", () => {
  it("renders the Dashboard placeholder at /", () => {
    const queryClient = new QueryClient();
    const router = createMemoryRouter(
      [
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
      ],
      { initialEntries: ["/"] },
    );

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    // The shell's Sidebar also renders a "Dashboard" nav label, so scope the
    // assertion to the routed content rather than the whole document.
    const content = screen.getByTestId("content-inner");
    expect(within(content).getByText("Dashboard")).toBeTruthy();
  });
});
