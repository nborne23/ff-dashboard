// The team-scoping UX: which team is on screen, switching between teams without losing
// the section, and moving between a team's three views.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  createMemoryRouter,
  RouterProvider,
  useLocation,
} from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../../App";
import { TeamContextBar } from "./TeamContextBar";
import { Sidebar } from "./Sidebar";
import { useUiStore } from "../../stores/ui";
import { parseTeamRoute } from "../../hooks/teamRoute";

const TEAMS = [
  { id: "espn:l-1-t-2", name: "Highland Bombers" },
  { id: "yahoo:l-9-t-3", name: "Rival Squad" },
];

function stubTeams(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          data: { teams: TEAMS },
          meta: {
            live_state: "off_day",
            as_of: new Date().toISOString(),
            next_refresh_at: new Date().toISOString(),
            current_week: 1,
            platforms: {},
          },
        }),
    })) as unknown as typeof fetch,
  );
}

/** Echoes the current path so a navigation can be asserted on directly. */
function PathProbe() {
  return <span data-testid="path">{useLocation().pathname}</span>;
}

/** Renders the bar driven by the router, the way App.tsx does. */
function RoutedBar() {
  const { pathname } = useLocation();
  const match = parseTeamRoute(pathname);
  return match ? <TeamContextBar teamId={match.teamId} section={match.section} /> : null;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <RoutedBar />
        <PathProbe />
        <Routes>
          <Route path="*" element={null} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TeamContextBar", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useUiStore.setState({ activeTeamId: null });
  });

  it("names the team the route addresses", async () => {
    stubTeams();
    renderAt("/team/espn:l-1-t-2/h2h");
    await waitFor(() => expect(screen.getByText("Highland Bombers")).toBeTruthy());
  });

  it("marks the tab for the section on screen", async () => {
    stubTeams();
    renderAt("/team/espn:l-1-t-2/season");
    await waitFor(() => expect(screen.getByText("Highland Bombers")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Season" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(screen.getByRole("button", { name: "Matchup" }).getAttribute("aria-current")).toBeNull();
  });

  it("navigates to a sibling view of the SAME team when a tab is clicked", async () => {
    stubTeams();
    renderAt("/team/espn:l-1-t-2");
    await waitFor(() => expect(screen.getByText("Highland Bombers")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Matchup" }));
    expect(screen.getByTestId("path").textContent).toBe("/team/espn:l-1-t-2/h2h");
  });

  it("preserves the section when switching teams", async () => {
    // The point of the switcher: comparing two teams' matchups should not dump you back
    // on the other team's roster.
    stubTeams();
    renderAt("/team/espn:l-1-t-2/h2h");
    await waitFor(() => expect(screen.getByText("Highland Bombers")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Highland Bombers/ }));
    fireEvent.click(screen.getByRole("option", { name: /Rival Squad/ }));

    expect(screen.getByTestId("path").textContent).toBe("/team/yahoo:l-9-t-3/h2h");
  });

  it("disables the switcher when no teams are connected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            data: { teams: [] },
            meta: {
              live_state: "off_day",
              as_of: new Date().toISOString(),
              next_refresh_at: new Date().toISOString(),
              current_week: 1,
              platforms: {},
            },
          }),
      })) as unknown as typeof fetch,
    );
    renderAt("/team/espn:l-1-t-2");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Select a team/ }).hasAttribute("disabled")).toBe(
        true,
      ),
    );
  });
});

describe("Sidebar teams", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useUiStore.setState({ activeTeamId: null });
  });

  function renderSidebarAt(path: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <Sidebar />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("lists every team directly, each opening its roster from Game Day", async () => {
    stubTeams();
    renderSidebarAt("/");

    await waitFor(() =>
      expect(screen.getByText("Highland Bombers").closest("a")?.getAttribute("href")).toBe(
        "/team/espn:l-1-t-2",
      ),
    );
    expect(screen.getByText("Rival Squad").closest("a")?.getAttribute("href")).toBe(
      "/team/yahoo:l-9-t-3",
    );
  });

  it("keeps the current view when moving between teams", async () => {
    stubTeams();
    renderSidebarAt("/team/espn:l-1-t-2/season");

    await waitFor(() =>
      expect(screen.getByText("Rival Squad").closest("a")?.getAttribute("href")).toBe(
        "/team/yahoo:l-9-t-3/season",
      ),
    );
  });

  it("marks the team on screen as current", async () => {
    stubTeams();
    renderSidebarAt("/team/yahoo:l-9-t-3/h2h");

    await waitFor(() =>
      expect(screen.getByText("Rival Squad").closest("a")?.getAttribute("aria-current")).toBe(
        "page",
      ),
    );
    expect(
      screen.getByText("Highland Bombers").closest("a")?.getAttribute("aria-current"),
    ).toBeNull();
  });

  it("has no team-scoped view links that would have to guess a team", async () => {
    // Matchups / Season / Waivers / League used to sit here and silently resolve to the
    // last team viewed. Views now live only in the team header's tabs.
    stubTeams();
    renderSidebarAt("/");
    await waitFor(() => expect(screen.getByText("Rival Squad")).toBeTruthy());
    for (const label of ["Matchups", "Season", "Waivers", "League"]) {
      expect(screen.queryByText(label)).toBeNull();
    }
  });
});

describe("route -> remembered team wiring", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useUiStore.setState({ activeTeamId: null });
  });

  /**
   * Renders the real shell, so `useActiveTeamSync` actually runs. This is the test that
   * fails if visiting a team route stops writing the remembered team — which the
   * phone tab bar's Teams link depends on.
   */
  function renderShellAt(path: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <App />,
          children: [
            { index: true, element: null },
            { path: "team/:teamId/season", element: null },
          ],
        },
      ],
      { initialEntries: [path] },
    );
    return render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
  }

  function teamsTab(): HTMLAnchorElement {
    return document.querySelector(".tabbar a:nth-child(2)") as HTMLAnchorElement;
  }

  it("makes the tab bar's Teams link follow the team the route is showing", async () => {
    stubTeams();
    // The visited team is deliberately NOT teams[0], so a pass can't come from the
    // fallback.
    renderShellAt("/team/yahoo:l-9-t-3/season");

    await waitFor(() => expect(teamsTab().getAttribute("href")).toBe("/team/yahoo:l-9-t-3"));
    expect(useUiStore.getState().activeTeamId).toBe("yahoo:l-9-t-3");
  });

  it("falls back to the first team when the remembered one is gone", async () => {
    stubTeams();
    useUiStore.setState({ activeTeamId: "espn:disconnected-league" });
    renderShellAt("/");

    await waitFor(() => expect(teamsTab().getAttribute("href")).toBe("/team/espn:l-1-t-2"));
  });
});
