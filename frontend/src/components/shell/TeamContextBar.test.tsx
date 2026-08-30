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

describe("Sidebar team scoping", () => {
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

  it("points Matchups and Season at the remembered team, not the first one", async () => {
    stubTeams();
    useUiStore.setState({ activeTeamId: "yahoo:l-9-t-3" });
    renderSidebarAt("/");

    await waitFor(() =>
      expect(screen.getByText("Matchups").closest("a")?.getAttribute("href")).toBe(
        "/team/yahoo:l-9-t-3/h2h",
      ),
    );
    expect(screen.getByText("Season").closest("a")?.getAttribute("href")).toBe(
      "/team/yahoo:l-9-t-3/season",
    );
  });

  it("falls back to the first team when the remembered one is gone", async () => {
    stubTeams();
    useUiStore.setState({ activeTeamId: "espn:disconnected-league" });
    renderSidebarAt("/");

    await waitFor(() =>
      expect(screen.getByText("Matchups").closest("a")?.getAttribute("href")).toBe(
        "/team/espn:l-1-t-2/h2h",
      ),
    );
  });

  it("expands the team list on a team route", async () => {
    stubTeams();
    renderSidebarAt("/team/yahoo:l-9-t-3/season");
    await waitFor(() => expect(screen.getByText("Rival Squad")).toBeTruthy());
  });
});

describe("route -> remembered team wiring", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useUiStore.setState({ activeTeamId: null });
  });

  /**
   * Renders the real shell, so `useActiveTeamSync` actually runs. The Sidebar tests
   * above inject `activeTeamId` by hand — good isolation for `resolveTeamId`, but they
   * would all still pass with the sync hook deleted, because nothing in them asserts
   * that VISITING a team route writes the store. This is the test that fails if that
   * one wire is cut, which is the wire the whole feature hangs on.
   */
  function renderShellAt(path: string) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [{ path: "/", element: <App />, children: [{ path: "team/:teamId/season", element: null }] }],
      { initialEntries: [path] },
    );
    return render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
  }

  it("makes the sidebar's Matchups link follow the team the route is showing", async () => {
    stubTeams();
    // Nothing remembered yet, and the visited team is deliberately NOT teams[0] — so a
    // pass cannot come from the fallback.
    renderShellAt("/team/yahoo:l-9-t-3/season");

    await waitFor(() =>
      expect(screen.getByText("Matchups").closest("a")?.getAttribute("href")).toBe(
        "/team/yahoo:l-9-t-3/h2h",
      ),
    );
    expect(useUiStore.getState().activeTeamId).toBe("yahoo:l-9-t-3");
  });
});
