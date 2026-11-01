// The "Open in ESPN / Yahoo" link, alone and in the team header every team view shares.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeamContextBar } from "../shell/TeamContextBar";
import { SourceAppLinkButton } from "./SourceAppLink";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SourceAppLinkButton", () => {
  it("links an ESPN team out to ESPN in a new tab", () => {
    render(<SourceAppLinkButton teamId="espn:l-1234567-t-8" teamName="Highland Bombers" />);
    const link = screen.getByRole("link", { name: "Open in ESPN: Highland Bombers" });
    expect(link.getAttribute("href")).toBe(
      "https://fantasy.espn.com/football/team?leagueId=1234567&teamId=8",
    );
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.textContent).toBe("Open in ESPN");
  });

  it("links a Yahoo team out to Yahoo", () => {
    render(<SourceAppLinkButton teamId="yahoo:461.l.98765.t.4" />);
    const link = screen.getByRole("link", { name: "Open in Yahoo" });
    expect(link.getAttribute("href")).toBe("https://football.fantasysports.yahoo.com/f1/98765/4");
  });

  it("renders nothing for a team id it can't place", () => {
    const { container } = render(<SourceAppLinkButton teamId="sleeper:abc" />);
    expect(container.innerHTML).toBe("");
  });
});

describe("TeamContextBar source-app link", () => {
  function renderBar(teamId: string, teams: { id: string; name: string }[]) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify({
            data: { teams },
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
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <TeamContextBar teamId={teamId} section="roster" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("offers the team on screen, not another one, in its own platform's app", async () => {
    renderBar("yahoo:461.l.98765.t.4", [
      { id: "espn:l-1234567-t-8", name: "Highland Bombers" },
      { id: "yahoo:461.l.98765.t.4", name: "Rival Squad" },
    ]);
    const link = await screen.findByRole("link", { name: "Open in Yahoo: Rival Squad" });
    expect(link.getAttribute("href")).toBe("https://football.fantasysports.yahoo.com/f1/98765/4");
    expect(screen.getAllByTestId("source-app-link")).toHaveLength(1);
  });

  it("shows the link before the teams list has loaded, since the id alone builds it", () => {
    renderBar("espn:l-1234567-t-8", []);
    expect(screen.getByRole("link", { name: "Open in ESPN" }).getAttribute("href")).toBe(
      "https://fantasy.espn.com/football/team?leagueId=1234567&teamId=8",
    );
  });
});
