import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Topbar } from "./Topbar";
import { useLiveConnectionStore } from "../../stores/live";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

describe("Topbar refresh button", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("POSTs /api/admin/refresh and invalidates the teams query", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => jsonResponse(200, { ok: true }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    render(
      <QueryClientProvider client={queryClient}>
        <Topbar />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) === "/api/admin/refresh" &&
            (init?.method ?? "GET").toUpperCase() === "POST",
        ),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["teams"] });
    });
  });

  it("disables the button while the refresh is pending", async () => {
    let release: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => pending),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Topbar />
      </QueryClientProvider>,
    );

    const button = screen.getByRole("button", { name: "Refresh" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);

    fireEvent.click(button);

    await waitFor(() => {
      expect(button.disabled).toBe(true);
    });

    release(jsonResponse(200, { ok: true }));

    await waitFor(() => {
      expect(button.disabled).toBe(false);
    });
  });
});

// The live badge counts real `team.is_live` teams, and shows only when there are any.
describe("Topbar real-data wiring", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const meta = {
    live_state: "live",
    as_of: "2026-07-16T12:00:00Z",
    next_refresh_at: "2026-07-16T12:30:00Z",
    current_week: 1,
    platforms: { yahoo: { ok: true }, espn: { ok: true } },
  };

  function makeTeam(id: string, isLive: boolean) {
    return {
      id,
      league_id: "yahoo:l1",
      name: id,
      manager_name: "Nick",
      record: { w: 0, l: 0, t: 0 },
      rank: { current: 1, total: 10 },
      points_for: 0,
      points_against: 0,
      is_user_team: true,
      current_score: 10,
      current_opp_score: 5,
      current_opponent_name: "Opp",
      is_live: isLive,
      spark_last_6: [],
      accent_color: "#FF2D55",
    };
  }

  function installFetchMock() {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/teams/day-rings")) {
        return jsonResponse(200, {
          data: {
            days: [
              { letter: "T", rings: [{ value: 0.5, color: "#FF2D55" }] },
              { letter: "F", rings: [{ value: 0.2, color: "#FF2D55" }] },
            ],
            today_index: 0,
          },
          meta,
        });
      }
      if (url.startsWith("/api/teams")) {
        return jsonResponse(200, {
          data: { teams: [makeTeam("yahoo:l1.t1", true), makeTeam("yahoo:l1.t2", false)] },
          meta,
        });
      }
      return jsonResponse(200, { ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  function renderTopbar() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <Topbar />
      </QueryClientProvider>,
    );
  }

  it("shows the real count of live teams instead of a hardcoded number", async () => {
    installFetchMock();
    renderTopbar();

    await waitFor(() => {
      expect(screen.getByText("1 live")).toBeTruthy();
    });
  });

  it("hides the live badge entirely when nothing is live", async () => {
    // A permanent "0 live" trains the eye to skip the one badge meant to be noticed.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, { data: { teams: [makeTeam("yahoo:l1.t2", false)] }, meta }),
      ),
    );
    renderTopbar();

    await waitFor(() => {
      expect(screen.getByText(/^Updated /)).toBeTruthy();
    });
    expect(screen.queryByTestId("live-badge")).toBeNull();
  });

  it("is the one home for freshness, and swaps it for the disconnect message", async () => {
    installFetchMock();
    useLiveConnectionStore.setState({ connectionLostLong: true });
    renderTopbar();

    await waitFor(() => {
      expect(screen.getByText("Connection lost — retrying")).toBeTruthy();
    });
    expect(screen.queryByText(/^Updated /)).toBeNull();
    useLiveConnectionStore.setState({ connectionLostLong: false });
  });
});
