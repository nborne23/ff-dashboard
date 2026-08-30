import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GAME_DAY_DEFAULTS, useUiStore } from "../../stores/ui";
import type { Envelope, GameDayData, GameDayMatchup } from "../../types/api";
import { GAME_DAY_FIXTURE } from "./fixtures";
import GameDay from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function envelope(matchups: GameDayMatchup[]): Envelope<GameDayData> {
  return {
    data: { matchups },
    meta: {
      live_state: "live",
      as_of: "2026-09-13T18:00:00Z",
      next_refresh_at: "2026-09-13T18:00:30Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function renderGameDay(body: Envelope<GameDayData> = envelope(GAME_DAY_FIXTURE.matchups)) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse(200, body)),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GameDay />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function panels(): HTMLElement[] {
  return Array.from(document.querySelectorAll(".gd-panel"));
}

describe("GameDay", () => {
  beforeEach(() => {
    // The layout store is persisted, so reset it between tests or one test's
    // arrangement leaks into the next.
    useUiStore.setState({ gameDay: { ...GAME_DAY_DEFAULTS }, week: 2 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders exactly one panel per matchup in the envelope", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    expect(panels()).toHaveLength(GAME_DAY_FIXTURE.matchups.length);
    for (const matchup of GAME_DAY_FIXTURE.matchups) {
      expect(screen.getByTestId(`gd-panel-${matchup.team_id}`)).toBeTruthy();
    }
  });

  it("issues exactly one request for the whole screen, not one per panel", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));

    // Exactly one game-day request for six panels — the point of the bulk envelope
    // (design D5). The screen's other request is the shared /api/connections query that
    // every screen makes via usePlatformsDisconnected; what must NOT appear is a
    // per-team /h2h or /{id} call.
    expect(urls.filter((url) => url.includes("/api/teams/game-day"))).toHaveLength(1);
    expect(urls.some((url) => url.includes("/h2h"))).toBe(false);
  });

  it("reflects the arrangement on the stage and switching it changes data-layout", async () => {
    renderGameDay();
    const stage = await screen.findByTestId("gameday-stage");
    expect(stage.getAttribute("data-layout")).toBe("g3");

    fireEvent.click(screen.getByRole("button", { name: "4-column" }));
    expect(screen.getByTestId("gameday-stage").getAttribute("data-layout")).toBe("c4");
    expect(useUiStore.getState().gameDay.mode).toBe("c4");
  });

  it("renders the roster markup in the DOM at every arrangement (design D3)", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    // Visibility below 540px is CSS's job — jsdom does not evaluate @container, so what
    // a unit test can assert is that the markup is unconditionally PRESENT, which is
    // the property the design actually depends on.
    for (const mode of ["2-across", "3-across", "4-column", "Spotlight"]) {
      fireEvent.click(screen.getByRole("button", { name: mode }));
      expect(screen.getAllByTestId("gd-roster")).toHaveLength(GAME_DAY_FIXTURE.matchups.length);
    }
  });

  it("dims a settled panel even when every game_state is null (design D4 regression)", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    // Fixture 3 is is_complete with every slot state left null — exactly what discovery
    // writes. A dim derived from `game_state === "post"` would never fire here.
    const settled = screen.getByTestId("gd-panel-espn:t3");
    expect(settled.getAttribute("data-settled")).toBe("true");
    for (const slot of GAME_DAY_FIXTURE.matchups[2].slots) {
      expect(slot.home_state).toBeNull();
      expect(slot.away_state).toBeNull();
    }

    // And an in-play panel is not dimmed.
    expect(screen.getByTestId("gd-panel-yahoo:t1").getAttribute("data-settled")).toBeNull();
  });

  it("outlines a panel with live players and leaves a quiet one alone", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    expect(screen.getByTestId("gd-panel-yahoo:t1").getAttribute("data-live")).toBe("true");
    // Nothing has kicked off in fixture 6.
    expect(screen.getByTestId("gd-panel-espn:t6").getAttribute("data-live")).toBeNull();
  });

  it("shows TIED rather than a signed margin when the scores match", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const tied = screen.getByTestId("gd-panel-espn:t4");
    expect(within(tied).getByText("TIED")).toBeTruthy();
    expect(tied.querySelectorAll("[data-trailing='true']")).toHaveLength(0);
  });

  it("reports the true sub-50 win probability instead of the floored favorite view", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    // Fixture 2 is projected to lose by ~29. Head-to-Head's clamp would read 50%.
    const losing = screen.getByTestId("gd-panel-yahoo:t2");
    const winProbCell = within(losing)
      .getByText("Win prob")
      .parentElement!.querySelector(".gd-stat-value") as HTMLElement;
    const pct = Number(winProbCell.textContent!.replace("%", ""));
    expect(pct).toBeLessThan(50);
  });

  it("drag-reorder moves the panel and resets sortMode to manual", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    fireEvent.click(screen.getByRole("button", { name: "Closest" }));
    expect(useUiStore.getState().gameDay.sortMode).toBe("margin");

    const order = panels().map((p) => p.getAttribute("data-testid")!.replace("gd-panel-", ""));
    const [first, second] = order;

    const dragged = screen.getByTestId(`gd-panel-${second}`).querySelector(".gd-meta")!;
    const target = screen.getByTestId(`gd-panel-${first}`).querySelector(".gd-meta")!;
    fireEvent.dragStart(dragged);
    fireEvent.dragOver(target);
    fireEvent.drop(target);

    const state = useUiStore.getState().gameDay;
    // An auto-sort mode and a hand-placed order are mutually exclusive states.
    expect(state.sortMode).toBe("manual");
    expect(state.order[0]).toBe(second);
    expect(state.order[1]).toBe(first);
  });

  it("sorts by closest margin when that mode is selected", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    fireEvent.click(screen.getByRole("button", { name: "Closest" }));
    const first = panels()[0].getAttribute("data-testid");
    // The tied matchup has the smallest absolute margin.
    expect(first).toBe("gd-panel-espn:t4");
  });

  it("resize cycles the panel's span and persists it", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const handle = screen
      .getByTestId("gd-panel-yahoo:t1")
      .querySelector(".gd-resize-handle") as HTMLElement;

    fireEvent.pointerDown(handle);
    expect(useUiStore.getState().gameDay.spans["yahoo:t1"]).toEqual({ cols: 2, rows: 1 });

    fireEvent.pointerDown(handle);
    expect(useUiStore.getState().gameDay.spans["yahoo:t1"]).toEqual({ cols: 2, rows: 2 });

    fireEvent.pointerDown(handle);
    expect(useUiStore.getState().gameDay.spans["yahoo:t1"]).toEqual({ cols: 1, rows: 1 });
  });

  it("the disclosure sets a data-roster attribute rather than unmounting the roster", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const panel = () => screen.getByTestId("gd-panel-yahoo:t1");
    // No attribute at all when the user has expressed no preference, so the container
    // query is the only thing deciding (design D3).
    expect(panel().getAttribute("data-roster")).toBeNull();
    expect(within(panel()).getByTestId("gd-roster")).toBeTruthy();

    // The toggle asks for the opposite of what is actually rendered. jsdom applies no
    // stylesheet, so the roster reads as visible here and the first click therefore
    // SHUTS it — which is the direction that matters: it proves the override can beat
    // a roster the container query opened, not just one it closed.
    fireEvent.click(within(panel()).getByRole("button", { name: /MATCHUP/ }));
    expect(panel().getAttribute("data-roster")).toBe("shut");
    // Still mounted — the attribute overrides CSS, it does not gate the mount.
    expect(within(panel()).getByTestId("gd-roster")).toBeTruthy();
    expect(useUiStore.getState().gameDay.shutIds).toContain("yahoo:t1");

    // display:none now applies for real (the attribute rule is not container-scoped),
    // so the next click swings it back open.
    (within(panel()).getByTestId("gd-roster") as HTMLElement).style.display = "none";
    fireEvent.click(within(panel()).getByRole("button", { name: /MATCHUP/ }));
    expect(panel().getAttribute("data-roster")).toBe("open");

    const state = useUiStore.getState().gameDay;
    expect(state.openIds).toContain("yahoo:t1");
    // The two lists are mutually exclusive — an id is never in both.
    expect(state.shutIds).not.toContain("yahoo:t1");
  });

  it("expand-all and collapse-all drive the persisted openIds", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(useUiStore.getState().gameDay.openIds).toHaveLength(GAME_DAY_FIXTURE.matchups.length);

    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    // Collapse all is an EXPLICIT shut, not a clearing of preferences: clearing would
    // hand wide panels back to the container query, which would leave them open.
    expect(useUiStore.getState().gameDay.openIds).toEqual([]);
    expect(useUiStore.getState().gameDay.shutIds).toHaveLength(GAME_DAY_FIXTURE.matchups.length);
  });

  it("opens the spotlight from the control and closes it on Escape", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    fireEvent.click(screen.getByRole("button", { name: "Spotlight Highland Bombers" }));
    const overlay = screen.getByTestId("gameday-spotlight");
    // Spotlight always shows the roster, at its own density.
    const spotlit = overlay.querySelector(".gd-panel")!;
    expect(spotlit.getAttribute("data-spotlight")).toBe("true");
    expect(spotlit.getAttribute("data-roster")).toBe("open");

    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.queryByTestId("gameday-spotlight")).toBeNull();
  });

  it("opens the spotlight on a header double-click, not a single click", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const header = screen.getByTestId("gd-panel-yahoo:t1").querySelector(".gd-meta")!;
    // A single click on the header is the start of a reorder drag; binding spotlight to
    // it too would make both gestures unreliable.
    fireEvent.click(header);
    expect(screen.queryByTestId("gameday-spotlight")).toBeNull();

    fireEvent.doubleClick(header);
    expect(screen.getByTestId("gameday-spotlight")).toBeTruthy();
  });

  it("closes the spotlight on a backdrop click but not on a click inside it", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    fireEvent.click(screen.getByRole("button", { name: "Spotlight Highland Bombers" }));
    fireEvent.click(screen.getByTestId("gameday-spotlight").querySelector(".gd-spotlight-frame")!);
    expect(screen.queryByTestId("gameday-spotlight")).toBeTruthy();

    fireEvent.click(screen.getByTestId("gameday-spotlight"));
    expect(screen.queryByTestId("gameday-spotlight")).toBeNull();
  });

  it("appends a newly connected team the persisted order predates", async () => {
    useUiStore.setState({
      gameDay: { ...GAME_DAY_DEFAULTS, order: ["yahoo:t1", "yahoo:t2"] },
    });
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    // All six render, not just the two the stored order named.
    expect(panels()).toHaveLength(GAME_DAY_FIXTURE.matchups.length);
    expect(screen.getByTestId("gd-panel-espn:t6")).toBeTruthy();
  });

  it("ignores a persisted id that is no longer in the envelope", async () => {
    useUiStore.setState({
      gameDay: { ...GAME_DAY_DEFAULTS, order: ["yahoo:departed", "yahoo:t1"] },
    });
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    expect(panels()).toHaveLength(GAME_DAY_FIXTURE.matchups.length);
    expect(screen.queryByTestId("gd-panel-yahoo:departed")).toBeNull();
  });

  it("summarizes the matchup, leading, and live counts in the header", async () => {
    renderGameDay();
    await screen.findByTestId("gameday-stage");

    const subtitle = document.querySelector(".large-subtitle") as HTMLElement;
    expect(subtitle.textContent).toContain("6 matchups");
    // Fixture: t1, t3, t4(tied, not leading), t6 lead => 3 strictly leading.
    expect(within(subtitle).getByText(/^3 leading$/)).toBeTruthy();
    // 6 + 4 + 2 live slot-sides across the three in-play fixtures.
    expect(within(subtitle).getByText(/^12 live$/)).toBeTruthy();
  });

  it("renders the shared empty state when neither platform is connected", async () => {
    renderGameDay(
      (() => {
        const body = envelope([]);
        body.meta.platforms = {
          yahoo: { ok: false, error: "not_connected" },
          espn: { ok: false, error: "not_connected" },
        };
        return body;
      })(),
    );

    expect(await screen.findByTestId("gameday-empty")).toBeTruthy();
    expect(screen.queryByTestId("gameday-stage")).toBeNull();
    expect(screen.queryByTestId("gameday-controls")).toBeNull();
  });

  it("renders the shared error card when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(500, { detail: { code: "boom", message: "nope" } })),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <GameDay />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("gameday-error")).toBeTruthy();
  });
});

describe("GameDay density bands", () => {
  beforeEach(() => {
    useUiStore.setState({ gameDay: { ...GAME_DAY_DEFAULTS }, week: 2 });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // Task 7.9, implemented honestly. The change's task text asks to "snapshot the four
  // density bands by setting explicit panel widths", but jsdom does not evaluate
  // `@container` at all — four such snapshots would be byte-identical and would pass
  // while proving nothing about the ladder. design.md's own Risks section concedes this
  // and assigns the ladder itself to the visual-diff pass (task 8.4, which needs a
  // browser and is not completable here).
  //
  // What a unit test CAN prove is the property the design leans on: the panel opts into
  // container queries, and its structure is identical at every width — no width-measuring
  // JavaScript is deciding anything, so widening a panel can only change CSS.
  it.each([320, 480, 700, 1000])("renders identical structure at %ipx", async (width) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, envelope([GAME_DAY_FIXTURE.matchups[0]]))),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <GameDay />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByTestId("gameday-stage");

    const panel = screen.getByTestId("gd-panel-yahoo:t1");
    panel.style.width = `${width}px`;

    expect(panel.querySelectorAll(".gd-row")).toHaveLength(
      GAME_DAY_FIXTURE.matchups[0].slots.length,
    );
    expect(panel.querySelector(".gd-roster")).toBeTruthy();
    expect(panel.querySelector(".gd-scores")).toBeTruthy();
    expect(panel.querySelectorAll(".gd-stat")).toHaveLength(3);
    expect(panel.innerHTML).toMatchSnapshot();
  });
});
