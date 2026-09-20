import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { routeChildren } from "./routes";

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, text: async () => JSON.stringify({ data: {} }) })),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/", element: <App />, children: routeChildren }], {
    initialEntries: [path],
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("routes", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders Game Day at /", () => {
    renderAt("/");

    // The Sidebar renders a "Game Day" nav label too, so scope to the routed content.
    const content = screen.getByTestId("content-inner");
    expect(within(content).getByText("Game Day")).toBeTruthy();
  });

  it("keeps the Dashboard reachable at /dashboard", () => {
    renderAt("/dashboard");

    const content = screen.getByTestId("content-inner");
    expect(within(content).getByText("Dashboard")).toBeTruthy();
  });

  it("redirects the old /gameday path to / with its week intact", () => {
    const router = renderAt("/gameday?week=2");

    expect(router.state.location.pathname).toBe("/");
    expect(router.state.location.search).toBe("?week=2");
  });
});
