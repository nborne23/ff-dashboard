// Task 8.9: the disconnect fallback in the sidebar footer. The >30s timing itself is
// owned and tested by useLiveEvents (api/events.test.tsx) — here we only check that the
// footer renders the right thing for each `connectionLostLong` state.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";
import { useLiveConnectionStore } from "../../stores/live";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function resetLiveStore(): void {
  useLiveConnectionStore.setState({
    connected: false,
    liveState: "off_day",
    lastEventAt: null,
    connectionLostLong: false,
    liveTierSeconds: null,
  });
}

function renderSidebar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sidebar footer", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    resetLiveStore();
  });

  it("shows a freshness label when the connection is fine", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, {
          data: { teams: [] },
          meta: {
            live_state: "off_day",
            as_of: new Date().toISOString(),
            next_refresh_at: new Date().toISOString(),
            platforms: {},
          },
        }),
      ),
    );

    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText(/Last updated/)).toBeTruthy();
    });
    expect(screen.queryByText("Live connection lost — retrying")).toBeNull();
  });

  it("shows the disconnect message instead of freshness once connectionLostLong is true", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { ok: true })),
    );
    useLiveConnectionStore.setState({ connectionLostLong: true });

    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText("Live connection lost — retrying")).toBeTruthy();
    });
    expect(screen.queryByText(/Last updated/)).toBeNull();
  });

  it("applies the .lost modifier to the pulse dot while disconnected", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { ok: true })),
    );
    useLiveConnectionStore.setState({ connectionLostLong: true });

    const { container } = renderSidebar();

    expect(container.querySelector(".footer .pulse.lost")).toBeTruthy();
  });

  it("does not apply the .lost modifier while connected", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { ok: true })),
    );

    const { container } = renderSidebar();

    expect(container.querySelector(".footer .pulse.lost")).toBeNull();
  });
});
