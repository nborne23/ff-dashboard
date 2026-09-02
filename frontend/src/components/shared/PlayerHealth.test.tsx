import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, PlayerInjuryData } from "../../types/api";
import { InjuryBadge } from "./InjuryBadge";
import { isNoteworthy } from "./injuryLabels";
import { PlayerHealth } from "./PlayerHealth";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function envelope(data: PlayerInjuryData): Envelope<PlayerInjuryData> {
  return {
    data,
    meta: {
      live_state: "off_day",
      as_of: "2026-09-02T12:00:00Z",
      next_refresh_at: "2026-09-02T12:30:00Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function stubFetch(data: PlayerInjuryData) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(envelope(data)),
    })) as unknown as typeof fetch,
  );
}

describe("InjuryBadge", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the code and a spelled-out label", () => {
    render(<InjuryBadge status="IR" />);
    const badge = screen.getByTestId("injury-badge");
    expect(badge.textContent).toBe("IR");
    // The code carries the meaning for anyone who can't distinguish the pill colors.
    expect(badge.getAttribute("aria-label")).toBe("Injured Reserve");
  });

  it.each(["ACTIVE", null, undefined] as const)("renders nothing for %s", (status) => {
    const { container } = render(<InjuryBadge status={status} />);
    // A healthy pill on every row would bury the two rows that matter; null means
    // "unknown", which must not be drawn as a claim either way.
    expect(container.innerHTML).toBe("");
    expect(isNoteworthy(status)).toBe(false);
  });

  it("is a plain span with no dialog when given no onClick", () => {
    render(<InjuryBadge status="Q" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("PlayerHealth", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens the detail dialog and shows the injury facts and update", async () => {
    stubFetch({
      player_id: "espn:p-4428209",
      injury_status: "IR",
      detail_supported: true,
      report: {
        status: "Injured Reserve",
        injury_type: "Knee - PCL",
        location: "Leg",
        detail: "Surgery",
        side: "Right",
        return_date: "2027-02-15",
        short_comment: "Season-ending surgery to repair the PCL.",
        long_comment: "A 6-to-12 month recovery timeline.",
        reported_at: "2026-08-13T15:11:00Z",
        fetched_at: "2026-09-02T12:00:00Z",
      },
    });

    render(<PlayerHealth playerId="espn:p-4428209" playerName="Ricky Pearsall" status="IR" />, {
      wrapper,
    });
    fireEvent.click(screen.getByTestId("injury-badge"));

    const panel = await screen.findByRole("dialog");
    expect(panel.getAttribute("aria-label")).toBe("Ricky Pearsall health detail");
    await waitFor(() => expect(screen.getByText("Knee - PCL (Right)")).toBeTruthy());
    expect(screen.getByText("Surgery")).toBeTruthy();
    expect(screen.getByText(/Season-ending surgery/)).toBeTruthy();
  });

  it('hides ESPN\'s literal "Not Specified" rather than rendering it as a fact', async () => {
    stubFetch({
      player_id: "espn:p-1",
      injury_status: "Q",
      detail_supported: true,
      report: {
        status: "Questionable",
        injury_type: "Finger",
        location: "Not Specified",
        detail: "Not Specified",
        side: "Not Specified",
        return_date: null,
        short_comment: "Did not practice Wednesday.",
        long_comment: null,
        reported_at: null,
        fetched_at: "2026-09-02T12:00:00Z",
      },
    });

    render(<PlayerHealth playerId="espn:p-1" playerName="Kyle Juszczyk" status="Q" />, {
      wrapper,
    });
    fireEvent.click(screen.getByTestId("injury-badge"));

    await screen.findByText(/Did not practice Wednesday/);
    expect(screen.queryByText(/Not Specified/)).toBeNull();
    // The one real detail still shows, with no "(Not Specified)" side suffix.
    expect(screen.getByText("Finger")).toBeTruthy();
  });

  it("says detail is unavailable rather than 'no injury' for a Yahoo player", async () => {
    stubFetch({
      player_id: "yahoo:p-30123",
      injury_status: "Q",
      detail_supported: false,
      report: null,
    });

    render(<PlayerHealth playerId="yahoo:p-30123" playerName="Some Player" status="Q" />, {
      wrapper,
    });
    fireEvent.click(screen.getByTestId("injury-badge"));

    expect(await screen.findByText(/aren’t available for this player/)).toBeTruthy();
  });

  it("closes on Escape", async () => {
    stubFetch({
      player_id: "espn:p-1",
      injury_status: "O",
      detail_supported: true,
      report: null,
    });

    render(<PlayerHealth playerId="espn:p-1" playerName="Someone" status="O" />, { wrapper });
    fireEvent.click(screen.getByTestId("injury-badge"));
    await screen.findByRole("dialog");

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
