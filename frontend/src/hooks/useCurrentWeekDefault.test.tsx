import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useUiStore } from "../stores/ui";
import type { Meta } from "../types/api";
import { useCurrentWeekDefault } from "./useCurrentWeekDefault";

function meta(currentWeek: number): Meta {
  return {
    live_state: "off_day",
    as_of: "2026-09-20T18:00:00Z",
    next_refresh_at: "2026-09-20T18:30:00Z",
    platforms: { yahoo: { ok: true }, espn: { ok: true } },
    current_week: currentWeek,
  };
}

function stubTeams(currentWeek: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ data: { teams: [] }, meta: meta(currentWeek) }),
    })),
  );
}

function stubFailure() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 500,
      text: async () => JSON.stringify({ error: { code: "boom", message: "boom" } }),
    })),
  );
}

function Probe() {
  useCurrentWeekDefault();
  return <span data-testid="week">{useUiStore((s) => s.week)}</span>;
}

function renderProbe() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe />
    </QueryClientProvider>,
  );
}

describe("useCurrentWeekDefault", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
    useUiStore.setState({ week: 1, weekPinned: false });
  });

  it("moves the week off the placeholder and onto the live one", async () => {
    stubTeams(3);
    renderProbe();

    await waitFor(() => expect(screen.getByTestId("week").textContent).toBe("3"));
    expect(useUiStore.getState().weekPinned).toBe(true);
  });

  it("leaves a week the user already chose alone", async () => {
    // The Topbar's arrows and the URL's ?week= both pin through `setWeek`. A deep link
    // to week 2 must survive the envelope landing on week 3.
    stubTeams(3);
    useUiStore.setState({ week: 2, weekPinned: true });
    renderProbe();

    await waitFor(() => expect(screen.getByTestId("week").textContent).toBe("2"));
  });

  it("does not pin the week when the request fails", async () => {
    // Reading `?? 1` off a failed query would pin a fabricated week 1 for the rest of
    // the session, and the retry that succeeds would then be ignored.
    stubFailure();
    renderProbe();

    await waitFor(() => expect(useUiStore.getState().weekPinned).toBe(false));
    expect(screen.getByTestId("week").textContent).toBe("1");
  });

  it("never persists the pin — a restored display has to seed again", async () => {
    // `weekPinned` must stay out of the store's `partialize`, alongside `week` itself.
    // If it rehydrated as true, a wall display restarted by the LaunchAgent would sit
    // on the placeholder week 1 all season — the exact bug this hook exists to prevent.
    stubTeams(5);
    renderProbe();
    await waitFor(() => expect(useUiStore.getState().weekPinned).toBe(true));

    const persisted = JSON.parse(localStorage.getItem("gridiron-ui-tweaks") ?? "{}");
    expect(persisted.state?.weekPinned).toBeUndefined();
    expect(persisted.state?.week).toBeUndefined();
  });
});
