import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConnectionStatus, Platform } from "../../api/connections";
import type { LeagueSetting } from "../../api/leagues";
import type { LiveTier } from "../../api/settings";
import Settings from "./index";

const VALID_SWID = "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}";
const VALID_ESPN_S2 = "cookie-value";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function emptyStatus(platform: Platform): ConnectionStatus {
  return { platform, is_connected: false, display_name: null, last_verified_at: null };
}

function league(overrides: Partial<LeagueSetting> = {}): LeagueSetting {
  return {
    id: "espn:1234567",
    platform: "espn",
    platform_id: "1234567",
    name: "Office League",
    season: 2025,
    team_count: 10,
    scoring_type: "standard",
    current_week: 14,
    is_enabled: true,
    ...overrides,
  };
}

interface RefreshRunResult {
  id: number;
  job_name: string;
  run_at: string;
  ok: boolean;
  error: string | null;
  duration_ms: number;
}

interface MockState {
  yahoo: ConnectionStatus;
  espn: ConnectionStatus;
  leagues: LeagueSetting[];
  liveTier: LiveTier;
  refreshRuns: RefreshRunResult[];
}

function installFetchMock(initial: Partial<MockState> = {}) {
  const state: MockState = {
    yahoo: initial.yahoo ?? emptyStatus("yahoo"),
    espn: initial.espn ?? emptyStatus("espn"),
    leagues: initial.leagues ?? [league()],
    liveTier: initial.liveTier ?? "30s",
    refreshRuns: initial.refreshRuns ?? [],
  };

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();

    if (url === "/api/connections" && method === "GET") {
      return jsonResponse(200, [state.yahoo, state.espn]);
    }

    if (url === "/api/connections/yahoo/start" && method === "POST") {
      return jsonResponse(200, { auth_url: "https://yahoo.example/oauth/start" });
    }

    if (url === "/api/connections/espn/test" && method === "POST") {
      const body = JSON.parse(String(init?.body)) as { swid: string; espn_s2: string };
      if (body.swid !== VALID_SWID || body.espn_s2 !== VALID_ESPN_S2) {
        return jsonResponse(422, {
          detail: { code: "auth_required", message: "ESPN rejected the provided cookies" },
        });
      }
      state.espn = {
        platform: "espn",
        is_connected: true,
        display_name: null,
        last_verified_at: new Date().toISOString(),
      };
      return jsonResponse(200, state.espn);
    }

    if (url.startsWith("/api/connections/") && method === "DELETE") {
      const platform = url.split("/").pop() as Platform;
      state[platform] = emptyStatus(platform);
      return jsonResponse(204, undefined);
    }

    if (url === "/api/leagues" && method === "GET") {
      return jsonResponse(200, state.leagues);
    }

    if (url.startsWith("/api/leagues/") && method === "PATCH") {
      const leagueId = decodeURIComponent(url.slice("/api/leagues/".length));
      const body = JSON.parse(String(init?.body)) as { is_enabled: boolean };
      const target = state.leagues.find((l) => l.id === leagueId);
      if (!target) return jsonResponse(404, { detail: { code: "league_not_found" } });
      target.is_enabled = body.is_enabled;
      return jsonResponse(200, target);
    }

    if (url === "/api/settings" && method === "GET") {
      return jsonResponse(200, { live_tier: state.liveTier });
    }

    if (url === "/api/settings/live-tier" && method === "POST") {
      const body = JSON.parse(String(init?.body)) as { live_tier: LiveTier };
      state.liveTier = body.live_tier;
      return jsonResponse(200, { live_tier: state.liveTier });
    }

    if (url === "/api/admin/refresh" && method === "POST") {
      return jsonResponse(200, { id: 1, job_name: "sync_discovery", ok: true, error: null });
    }

    if (url.startsWith("/api/admin/refresh-runs") && method === "GET") {
      return jsonResponse(200, state.refreshRuns);
    }

    if (url === "/api/cache" && method === "DELETE") {
      return jsonResponse(204, undefined);
    }

    if (url === "/api/export.json" && method === "GET") {
      return jsonResponse(200, { exported_at: "2026-07-16T00:00:00Z", leagues: [] });
    }

    throw new Error(`Unhandled fetch in test: ${method} ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state };
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>,
  );
}

describe("Settings", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders both platform rows from a mocked GET", async () => {
    installFetchMock({
      yahoo: {
        platform: "yahoo",
        is_connected: true,
        display_name: "gritty.linebacker",
        last_verified_at: new Date().toISOString(),
      },
      espn: emptyStatus("espn"),
    });

    renderSettings();

    expect(await screen.findByText("Yahoo Fantasy")).toBeTruthy();
    expect(screen.getByText("ESPN Fantasy")).toBeTruthy();
    expect(screen.getByText(/Connected as gritty\.linebacker/)).toBeTruthy();
    expect(screen.getByText("Not connected")).toBeTruthy();
  });

  it("shows a connected status after a successful ESPN test-connection", async () => {
    installFetchMock({ espn: emptyStatus("espn") });

    renderSettings();

    await screen.findByText("ESPN Fantasy");

    fireEvent.change(screen.getByLabelText("SWID"), { target: { value: VALID_SWID } });
    fireEvent.change(screen.getByLabelText("espn_s2"), { target: { value: VALID_ESPN_S2 } });
    fireEvent.click(screen.getByRole("button", { name: "Test Connection" }));

    await waitFor(() => {
      expect(screen.getByText(/Connected · just now/)).toBeTruthy();
    });
  });

  it("confirms and calls DELETE when Yahoo is disconnected", async () => {
    const { fetchMock } = installFetchMock({
      yahoo: {
        platform: "yahoo",
        is_connected: true,
        display_name: "gritty.linebacker",
        last_verified_at: new Date().toISOString(),
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderSettings();

    const yahooSwitch = await screen.findByRole("switch", { name: "Yahoo Fantasy connection" });
    fireEvent.click(yahooSwitch);

    expect(window.confirm).toHaveBeenCalled();

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) === "/api/connections/yahoo" &&
            (init?.method ?? "GET").toUpperCase() === "DELETE",
        ),
      ).toBe(true);
    });
  });

  // --- EspnLeaguesCard (task 7.3) ------------------------------------------------------

  it("lists ESPN leagues and toggles enable via PATCH", async () => {
    const { fetchMock, state } = installFetchMock({
      leagues: [
        league({ id: "espn:1", name: "Office League" }),
        league({ id: "yahoo:1", platform: "yahoo", name: "Yahoo League" }),
      ],
    });

    renderSettings();

    expect(await screen.findByText("Office League")).toBeTruthy();
    // Only the ESPN league renders in this card — the Yahoo one is filtered out.
    expect(screen.queryByText("Yahoo League")).toBeNull();
    expect(screen.getByText("ESPN · 2025 · 10 teams · standard scoring")).toBeTruthy();

    const toggle = screen.getByRole("switch", { name: "Office League enabled" });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) === "/api/leagues/espn:1" &&
            (init?.method ?? "GET").toUpperCase() === "PATCH" &&
            JSON.parse(String(init?.body)).is_enabled === false,
        ),
      ).toBe(true);
    });
    expect(state.leagues.find((l) => l.id === "espn:1")?.is_enabled).toBe(false);
  });

  it("shows an empty state when no ESPN leagues are found", async () => {
    installFetchMock({ leagues: [] });

    renderSettings();

    expect(await screen.findByText("No ESPN leagues found")).toBeTruthy();
  });

  // --- PreferencesCard (task 7.4) ------------------------------------------------------

  it("changes the live-refresh tier via the segmented control", async () => {
    const { fetchMock } = installFetchMock({ liveTier: "30s" });

    renderSettings();

    await screen.findByText("Polling frequency");
    const button10s = screen.getByRole("button", { name: "10s" });
    fireEvent.click(button10s);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) === "/api/settings/live-tier" &&
            (init?.method ?? "GET").toUpperCase() === "POST" &&
            JSON.parse(String(init?.body)).live_tier === "10s",
        ),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(button10s.className).toContain("active");
    });
  });

  it("toggles a notification switch without hitting the network", async () => {
    const { fetchMock } = installFetchMock();

    renderSettings();

    const switchEl = await screen.findByRole("switch", { name: "Red zone alerts" });
    expect(switchEl.getAttribute("aria-checked")).toBe("true");

    fireEvent.click(switchEl);

    expect(switchEl.getAttribute("aria-checked")).toBe("false");
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("notif"))).toBe(false);
  });

  // --- AppearanceCard (task 7.5) -------------------------------------------------------

  it("switches the active theme segment client-side", async () => {
    renderSettings();

    await screen.findByText("Appearance");
    const lightButton = screen.getByRole("button", { name: "Light" });
    expect(lightButton.className).not.toContain("active");

    fireEvent.click(lightButton);

    expect(lightButton.className).toContain("active");
  });

  it("selects an accent color swatch", async () => {
    renderSettings();

    await screen.findByText("Accent color");
    const greenSwatch = screen.getByRole("button", { name: "Accent color #30D158" });
    expect(greenSwatch.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(greenSwatch);

    expect(greenSwatch.getAttribute("aria-pressed")).toBe("true");
  });

  // --- DataManagementCard (task 7.6) ---------------------------------------------------

  it("clears the cache via DELETE /api/cache", async () => {
    const { fetchMock } = installFetchMock();

    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Clear" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) === "/api/cache" && (init?.method ?? "GET").toUpperCase() === "DELETE",
        ),
      ).toBe(true);
    });
  });

  it("exports data by fetching the export endpoint and triggering a download", async () => {
    const { fetchMock } = installFetchMock();
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    // jsdom doesn't implement Blob URLs — attach mocks directly to the real URL
    // constructor rather than replacing the global (URL is also a constructor other
    // code in this render tree may rely on, e.g. react-router's useSearchParams).
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Export JSON" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/export.json")).toBe(
        true,
      );
    });
    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalled();
    });
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("confirms and disconnects both platforms", async () => {
    const { fetchMock } = installFetchMock({
      yahoo: { platform: "yahoo", is_connected: true, display_name: null, last_verified_at: null },
      espn: { platform: "espn", is_connected: true, display_name: null, last_verified_at: null },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => {
      const deletedPlatforms = fetchMock.mock.calls
        .filter(
          ([input, init]) =>
            String(input).startsWith("/api/connections/") &&
            (init?.method ?? "GET").toUpperCase() === "DELETE",
        )
        .map(([input]) => String(input));
      expect(deletedPlatforms.sort()).toEqual(["/api/connections/espn", "/api/connections/yahoo"]);
    });
  });

  it("does not disconnect when the confirm dialog is dismissed", async () => {
    const { fetchMock } = installFetchMock();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));

    expect(window.confirm).toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input).startsWith("/api/connections/") &&
          (init?.method ?? "GET").toUpperCase() === "DELETE",
      ),
    ).toBe(false);
  });

  // --- "Last refresh" status line (task 11.2) ------------------------------------------

  it("shows a successful last-refresh status derived from GET /api/admin/refresh-runs", async () => {
    installFetchMock({
      refreshRuns: [
        {
          id: 1,
          job_name: "refresh_fantasy",
          run_at: new Date(Date.now() - 42_000).toISOString(),
          ok: true,
          error: null,
          duration_ms: 120,
        },
      ],
    });

    renderSettings();

    await waitFor(() => {
      expect(screen.getByText(/Last refresh: \d+s ago · ok/)).toBeTruthy();
    });
  });

  it("shows a failed last-refresh status with the error message", async () => {
    installFetchMock({
      refreshRuns: [
        {
          id: 2,
          job_name: "refresh_fantasy",
          run_at: new Date(Date.now() - 5_000).toISOString(),
          ok: false,
          error: "upstream_error (503)",
          duration_ms: 80,
        },
      ],
    });

    renderSettings();

    await waitFor(() => {
      expect(
        screen.getByText(/Last refresh: \d+s ago · failed: upstream_error \(503\)/),
      ).toBeTruthy();
    });
  });

  it("renders no last-refresh row when there is no run history yet", async () => {
    installFetchMock({ refreshRuns: [] });

    renderSettings();

    await screen.findByText("Data Management");
    expect(screen.queryByText(/Last refresh:/)).toBeNull();
  });
});
