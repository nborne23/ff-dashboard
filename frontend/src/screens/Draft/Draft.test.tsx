import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  BoardData,
  BoardMatchOut,
  BoardPlayerOut,
  DraftStateData,
  MatchesData,
  RecommendationsData,
  SlotPlanData,
} from "../../api/draft";
import type { Envelope } from "../../types/api";
import Draft from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function envelope<T>(data: T): Envelope<T> {
  return {
    data,
    meta: {
      live_state: "off_day",
      as_of: "2026-08-23T12:00:00Z",
      next_refresh_at: "2026-08-23T12:30:00Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function makeBoardPlayer(overrides: Partial<BoardPlayerOut> = {}): BoardPlayerOut {
  return {
    id: 1,
    name: "Bijan Robinson",
    position: "RB",
    nfl_team: "ATL",
    bye: 5,
    adp_rank: 1,
    overall_tier: 1,
    positional_tier: 1,
    risk_score: 1,
    unpriced_risk: false,
    flags: [],
    adp: 1.2,
    adp_round: 1,
    risk: "low",
    rookie: false,
    out_for_season: false,
    note: null,
    thesis: null,
    take_in_round: null,
    is_drafted: false,
    drafted_overall_pick: null,
    drafted_by_team: null,
    is_my_pick: false,
    sleeper_category: null,
    catalyst: null,
    format_fit: null,
    injury_tags: [],
    analyst_takes: [],
    overall_tier_label: null,
    positional_tier_label: null,
    ...overrides,
  };
}

function makeBoard(players: BoardPlayerOut[]): BoardData {
  return { players };
}

function makeState(overrides: Partial<DraftStateData> = {}): DraftStateData {
  return {
    picks: [],
    current_overall_pick: 1,
    current_round: 1,
    picks_until_next: 0,
    my_upcoming_picks: [1, 24],
    roster: {
      starters: [
        { slot: "QB", position_group: "QB", filled: false, player: null },
        { slot: "RB1", position_group: "RB", filled: false, player: null },
        { slot: "RB2", position_group: "RB", filled: false, player: null },
        { slot: "FLEX1", position_group: "FLEX", filled: false, player: null },
        { slot: "FLEX2", position_group: "FLEX", filled: false, player: null },
      ],
      bench: [],
      bye_collisions: [],
    },
    settings_conflicts: [
      {
        field: "teams",
        static_value: 12,
        espn_value: null,
        resolved_value: 12,
        confirmed_by_espn: false,
        note: "",
      },
    ],
    session_status: "manual",
    league_teams: 12,
    draft_over: false,
    ...overrides,
  };
}

function makeRecommendations(overrides: Partial<RecommendationsData> = {}): RecommendationsData {
  return {
    current_overall_pick: 1,
    picks_until_next: 0,
    shortlist: [
      {
        candidate: {
          name: "Bijan Robinson",
          position: "RB",
          nfl_team: "ATL",
          bye: 5,
          adp_rank: 1,
          overall_tier: 1,
          positional_tier: 1,
          risk_score: 1,
          unpriced_risk: false,
          flags: [],
        },
        score: 4.2,
        components: { value: 1, tier_urgency: 1, need: 1, risk: 0, flags: 0 },
        reason: "Best available value at ADP rank 1.",
        fired_rule_ids: ["_value_calc"],
      },
    ],
    tier_alarms: [{ position: "RB", tier: 1, remaining: 2, picks_until_next: 10 }],
    bye_collisions: [],
    positional_runs: [],
    advisories: ["This league starts no kicker -- never draft one."],
    turn_pairs: [],
    ...overrides,
  };
}

function makeSlotPlan(overrides: Partial<SlotPlanData> = {}): SlotPlanData {
  return {
    applicable: true,
    user_draft_slot: 1,
    structural_note: null,
    pick_numbers: [1],
    entries: [],
    unplanned_pick_numbers: [],
    ...overrides,
  };
}

function makeBoardMatch(overrides: Partial<BoardMatchOut> = {}): BoardMatchOut {
  return {
    board_player_name: "Bijan Robinson",
    espn_player_id: 4430,
    match_method: "exact",
    match_confidence: 1.0,
    candidates: [],
    ...overrides,
  };
}

function makeMatches(overrides: Partial<MatchesData> = {}): MatchesData {
  return {
    matches: [makeBoardMatch()],
    method_counts: { exact: 1 },
    below_threshold_count: 0,
    ...overrides,
  };
}

function renderDraft(options: {
  board?: BoardPlayerOut[];
  state?: Partial<DraftStateData>;
  recommendations?: Partial<RecommendationsData>;
  slotPlan?: Partial<SlotPlanData>;
  matches?: Partial<MatchesData>;
}) {
  const board = options.board ?? [makeBoardPlayer()];
  const state = makeState(options.state);
  const recommendations = makeRecommendations(options.recommendations);
  const slotPlan = makeSlotPlan(options.slotPlan);
  const matches = makeMatches(options.matches);

  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.includes("/api/draft/board")) return jsonResponse(200, envelope(makeBoard(board)));
      if (url.includes("/api/draft/slot-plan")) return jsonResponse(200, envelope(slotPlan));
      if (url.includes("/api/draft/recommendations"))
        return jsonResponse(200, envelope(recommendations));
      if (url.includes("/api/draft/current-pick") && method === "PUT")
        return jsonResponse(200, {
          current_overall_pick: 5,
          current_round: 1,
          picks_until_next: 0,
        });
      if (url.includes("/api/draft/picks/last") && method === "DELETE")
        return jsonResponse(200, { undone: null });
      if (url.includes("/api/draft/picks") && method === "POST")
        return jsonResponse(201, {
          id: 1,
          overall_pick: 1,
          round: 1,
          board_player_id: 1,
          espn_player_id: null,
          player_name: "Bijan Robinson",
          position: "RB",
          drafted_by_team: null,
          is_my_pick: true,
          source: "manual",
        });
      // POST /api/draft/matches/{name} must be checked before the plain GET
      // /api/draft/matches branch below -- both URLs contain "/api/draft/matches".
      // A write returns the bare BoardMatchOut payload (house convention for writes:
      // no Envelope), matching /picks and /current-pick above.
      if (url.includes("/api/draft/matches") && method === "POST")
        return jsonResponse(200, makeBoardMatch({ match_method: "override", match_confidence: 1 }));
      if (url.includes("/api/draft/matches")) return jsonResponse(200, envelope(matches));
      if (url.includes("/api/draft/state")) return jsonResponse(200, envelope(state));

      throw new Error(`unexpected fetch: ${method} ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/draft"]}>
        <Routes>
          <Route path="/draft" element={<Draft />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, queryClient };
}

describe("Draft screen", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the current pick, recommendations, and board once loaded", async () => {
    renderDraft({});

    expect(await screen.findByTestId("current-pick")).toBeTruthy();
    await screen.findByTestId("board-list");
    expect((await screen.findAllByText("Bijan Robinson")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Tier 1 RB down to 2 left/)).toBeTruthy();
    expect(screen.getByText(/no kicker/)).toBeTruthy();
  });

  it("never renders a kicker starter slot", async () => {
    renderDraft({});
    await screen.findByTestId("roster-panel");
    const roster = screen.getByTestId("roster-panel");
    expect(within(roster).queryByText("K")).toBeNull();
  });

  it("shows a persistent settings-conflict banner naming each unconfirmed field", async () => {
    renderDraft({});
    const banner = await screen.findByTestId("settings-conflict-banner");
    expect(within(banner).getByTestId("settings-conflict-unread")).toBeTruthy();
    expect(within(banner).getByText(/teams/)).toBeTruthy();
  });

  it("names a field where ESPN and the static config actively disagree", async () => {
    renderDraft({
      state: {
        settings_conflicts: [
          {
            field: "teams",
            static_value: 12,
            espn_value: 10,
            resolved_value: 10,
            confirmed_by_espn: true,
            note: "",
          },
        ],
      },
    });
    const banner = await screen.findByTestId("settings-conflict-banner");
    const item = within(banner).getByTestId("settings-conflict-disagreement");
    expect(item.textContent).toMatch(/teams/);
    expect(item.textContent).toMatch(/entered 12/);
    expect(item.textContent).toMatch(/ESPN says 10/);
  });

  it("names each field that could not be read from ESPN at all", async () => {
    renderDraft({
      state: {
        settings_conflicts: [
          {
            field: "_espn_connectivity",
            static_value: null,
            espn_value: null,
            resolved_value: "static fallback (unconfirmed)",
            confirmed_by_espn: false,
            note: "",
          },
          {
            field: "starters",
            static_value: { QB: 1 },
            espn_value: null,
            resolved_value: { QB: 1 },
            confirmed_by_espn: false,
            note: "",
          },
        ],
      },
    });
    const banner = await screen.findByTestId("settings-conflict-banner");
    expect(within(banner).getByTestId("settings-conflict-connectivity")).toBeTruthy();
    expect(within(banner).getByText(/No ESPN league settings are available/)).toBeTruthy();
    expect(within(banner).getByTestId("settings-conflict-unread").textContent).toMatch(/starters/);
  });

  it("greys out and strikes through a drafted player without removing it from the board", async () => {
    renderDraft({
      board: [
        makeBoardPlayer({
          name: "Drafted Guy",
          is_drafted: true,
          drafted_overall_pick: 1,
          is_my_pick: true,
        }),
      ],
    });

    const row = await screen.findByTestId("board-row");
    expect(row.className).toContain("drafted");
    expect(within(row).getByText("Drafted Guy")).toBeTruthy();
  });

  it("marking a player drafted POSTs to /api/draft/picks", async () => {
    const { fetchMock } = renderDraft({});
    await screen.findByTestId("board-list");

    fireEvent.click(screen.getByRole("button", { name: /Mark Bijan Robinson drafted by me/i }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        ([, init]) => init?.method === "POST" && String(fetchMock.mock.calls[0][0]),
      );
      expect(postCall).toBeTruthy();
    });
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(postCall).toBeTruthy();
    expect(String(postCall?.[0])).toContain("/api/draft/picks");
  });

  it("the undo button is rendered in the header, without needing to scroll to the board", async () => {
    const { fetchMock } = renderDraft({});
    const undoButton = await screen.findByTestId("undo-last-pick");

    fireEvent.click(undoButton);

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE");
      expect(deleteCall).toBeTruthy();
    });
  });

  it("setting the current pick directly PUTs to /api/draft/current-pick", async () => {
    const { fetchMock } = renderDraft({});
    await screen.findByTestId("current-pick");

    fireEvent.change(screen.getByLabelText("Set current overall pick"), {
      target: { value: "25" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set" }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
      expect(putCall).toBeTruthy();
    });
  });

  it("renders a bye-collision warning when the roster reports one", async () => {
    renderDraft({
      state: {
        roster: {
          starters: [],
          bench: [],
          bye_collisions: [{ bye: 9, count: 3, players: ["A", "B", "C"] }],
        },
      },
    });

    expect(await screen.findByTestId("bye-collision")).toBeTruthy();
    expect(screen.getByText(/Week 9: 3 starters share this bye/)).toBeTruthy();
  });

  it("renders the slot-1 plan with live sniped/yours status when applicable", async () => {
    renderDraft({
      slotPlan: {
        structural_note: "Picks 24 and 25 are back-to-back.",
        entries: [
          {
            picks: [1],
            label: "Pick 1",
            confidence: "high",
            rule: null,
            avoid: [],
            targets: [
              {
                name: "Bijan Robinson",
                group: null,
                sniped: false,
                drafted_by_me: true,
                drafted_by_team: null,
                still_available: false,
              },
            ],
          },
          {
            picks: [24, 25],
            label: "Picks 24 & 25",
            confidence: null,
            rule: "Take one from each group.",
            avoid: ["Josh Jacobs"],
            targets: [
              {
                name: "Sniped Guy",
                group: "group_b_rb_or_te",
                sniped: true,
                drafted_by_me: false,
                drafted_by_team: "Rival Team",
                still_available: false,
              },
              {
                name: "Out Guy",
                group: "group_b_rb_or_te",
                sniped: false,
                drafted_by_me: false,
                drafted_by_team: null,
                still_available: false,
              },
            ],
          },
        ],
      },
    });

    const plan = await screen.findByTestId("slot-plan");
    expect(within(plan).getByText(/Picks 24 and 25 are back-to-back/)).toBeTruthy();
    expect(within(plan).getByText(/Bijan Robinson · yours/)).toBeTruthy();
    expect(within(plan).getByText(/Sniped Guy · sniped by Rival Team/)).toBeTruthy();
    expect(within(plan).getByText(/Josh Jacobs/)).toBeTruthy();
    // Not sniped, not mine, but not in the live pool either (e.g. out for the season) --
    // must render distinctly from both a normal target and a sniped one.
    expect(within(plan).getByText(/Out Guy · unavailable/)).toBeTruthy();
  });

  it("does not render the slot-1 plan when the user isn't drafting from slot 1", async () => {
    renderDraft({ slotPlan: { applicable: false, user_draft_slot: 4 } });
    await screen.findByTestId("board-list");
    expect(screen.queryByTestId("slot-plan")).toBeNull();
  });

  it("shows an 'RB run in progress' banner when recommendations report a positional run", async () => {
    renderDraft({
      recommendations: { positional_runs: [{ position: "RB", count: 4 }] },
    });

    expect(await screen.findByTestId("positional-run")).toBeTruthy();
    expect(screen.getByText(/RB run in progress/)).toBeTruthy();
  });

  it("tapping a board row opens PlayerDetail with full scouting content", async () => {
    renderDraft({
      board: [
        makeBoardPlayer({
          name: "Jahmyr Gibbs",
          note: "Backup Pacheco has a sprained MCL.",
          thesis: "Locked-in bell cow.",
          sleeper_category: "ELITE",
          catalyst: "Bell-cow workload",
          format_fit: "Redraft",
          overall_tier_label: "TIER 1 -- ELITE ANCHORS",
          positional_tier_label: "TIER 1 -- Elite, workload-secure.",
          injury_tags: ["mcl"],
          analyst_takes: [
            {
              source: "The Fantasy Footballers",
              verified_accuracy: false,
              take: "RB1 overall",
              detail: "Consensus RB1.",
            },
          ],
        }),
      ],
    });
    await screen.findByTestId("board-list");

    fireEvent.click(screen.getByRole("button", { name: /View scouting detail for Jahmyr Gibbs/i }));

    const detail = await screen.findByTestId("player-detail");
    expect(within(detail).getByText("Locked-in bell cow.")).toBeTruthy();
    expect(within(detail).getByText(/Backup Pacheco has a sprained MCL/)).toBeTruthy();
    expect(within(detail).getByText("ELITE")).toBeTruthy();
    expect(within(detail).getByText("Bell-cow workload")).toBeTruthy();
    expect(within(detail).getByText(/TIER 1 -- ELITE ANCHORS/)).toBeTruthy();

    // Analyst take renders its source together with a visually-distinct accuracy badge.
    expect(within(detail).getByText("The Fantasy Footballers")).toBeTruthy();
    expect(within(detail).getByText("Unverified accuracy")).toBeTruthy();

    // Injury tags are labelled as a search aid, not curated fact.
    expect(within(detail).getByText("mcl")).toBeTruthy();
    expect(within(detail).getByText(/NOT a curated injury report/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Close Jahmyr Gibbs detail/i }));
    await waitFor(() => {
      expect(screen.queryByTestId("player-detail")).toBeNull();
    });
  });

  it("distinguishes a measured-accuracy analyst take from an unverified one", async () => {
    renderDraft({
      board: [
        makeBoardPlayer({
          name: "Verified Guy",
          analyst_takes: [
            { source: "Jeff Ratcliffe", verified_accuracy: true, take: "Top target", detail: null },
          ],
        }),
      ],
    });
    await screen.findByTestId("board-list");
    fireEvent.click(screen.getByRole("button", { name: /View scouting detail for Verified Guy/i }));

    const detail = await screen.findByTestId("player-detail");
    expect(within(detail).getByText("Measured accuracy")).toBeTruthy();
  });

  it("out-for-season players remain findable by search on the board", async () => {
    renderDraft({
      board: [
        makeBoardPlayer({ name: "Healthy Guy" }),
        makeBoardPlayer({ id: 2, name: "Season Ender", out_for_season: true }),
      ],
    });
    await screen.findByTestId("board-list");

    fireEvent.change(screen.getByLabelText("Search draft board by player name"), {
      target: { value: "Season Ender" },
    });

    expect(await screen.findByText("Season Ender")).toBeTruthy();
    expect(screen.getByText("OUT FOR SEASON")).toBeTruthy();
    expect(screen.queryByText("Healthy Guy")).toBeNull();
  });

  // Task 4.6 -- match resolution.
  it("reads as an affirmative 'all matched' state when nothing is below the confidence gate", async () => {
    renderDraft({
      matches: {
        matches: [makeBoardMatch(), makeBoardMatch({ board_player_name: "Ja'Marr Chase" })],
        method_counts: { exact: 2 },
        below_threshold_count: 0,
      },
    });

    const empty = await screen.findByTestId("match-resolution-empty");
    expect(within(empty).getByText(/All board players matched to ESPN/)).toBeTruthy();
    expect(screen.queryByTestId("match-resolution-list")).toBeNull();
  });

  it("lists players below the confidence gate with their candidates, without blocking the rest of the screen", async () => {
    renderDraft({
      matches: {
        matches: [
          makeBoardMatch({
            board_player_name: "Amb Guy",
            espn_player_id: null,
            match_method: "unmatched",
            match_confidence: 0.0,
            candidates: [
              {
                espn_player_id: 10,
                full_name: "Amb Guy",
                position: "WR",
                nfl_team: "SF",
                is_dst: false,
              },
              {
                espn_player_id: 11,
                full_name: "Amb Guy",
                position: "WR",
                nfl_team: "NYJ",
                is_dst: false,
              },
            ],
          }),
        ],
        method_counts: { unmatched: 1 },
        below_threshold_count: 1,
      },
    });

    const list = await screen.findByTestId("match-resolution-list");
    expect(within(list).getByText(/1 player needs ESPN match resolution/)).toBeTruthy();
    const row = within(list).getByTestId("match-resolution-row");
    expect(within(row).getByText("Amb Guy")).toBeTruthy();
    expect(
      within(row).getByRole("button", { name: /Match Amb Guy to Amb Guy, WR SF/ }),
    ).toBeTruthy();
    expect(
      within(row).getByRole("button", { name: /Match Amb Guy to Amb Guy, WR NYJ/ }),
    ).toBeTruthy();
    expect(
      within(row).getByRole("button", { name: /Record no ESPN match for Amb Guy/ }),
    ).toBeTruthy();

    // Non-blocking: the rest of the screen is fully present and usable alongside it.
    await screen.findByTestId("board-list");
    expect(screen.getByTestId("undo-last-pick")).toBeTruthy();
    expect(screen.getByTestId("recommendations")).toBeTruthy();
  });

  it("picking a candidate POSTs the override to /api/draft/matches/{name}", async () => {
    const { fetchMock } = renderDraft({
      matches: {
        matches: [
          makeBoardMatch({
            board_player_name: "Amb Guy",
            espn_player_id: null,
            match_method: "unmatched",
            match_confidence: 0.0,
            candidates: [
              {
                espn_player_id: 10,
                full_name: "Amb Guy",
                position: "WR",
                nfl_team: "SF",
                is_dst: false,
              },
            ],
          }),
        ],
        method_counts: { unmatched: 1 },
        below_threshold_count: 1,
      },
    });

    await screen.findByTestId("match-resolution-list");
    fireEvent.click(screen.getByRole("button", { name: /Match Amb Guy to Amb Guy, WR SF/ }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) => String(input).includes("/api/draft/matches/") && init?.method === "POST",
      );
      expect(call).toBeTruthy();
      const [url, init] = call!;
      expect(String(url)).toContain(encodeURIComponent("Amb Guy"));
      expect(JSON.parse(String(init?.body))).toEqual({ espn_player_id: 10 });
    });
  });

  it("'No ESPN match' POSTs an explicit null override", async () => {
    const { fetchMock } = renderDraft({
      matches: {
        matches: [
          makeBoardMatch({
            board_player_name: "Nobody Guy",
            espn_player_id: null,
            match_method: "unmatched",
            match_confidence: 0.0,
            candidates: [],
          }),
        ],
        method_counts: { unmatched: 1 },
        below_threshold_count: 1,
      },
    });

    const row = await screen.findByTestId("match-resolution-row");
    expect(within(row).getByText(/No ESPN candidates found/)).toBeTruthy();
    fireEvent.click(
      within(row).getByRole("button", { name: /Record no ESPN match for Nobody Guy/ }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) => String(input).includes("/api/draft/matches/") && init?.method === "POST",
      );
      expect(call).toBeTruthy();
      const [, init] = call!;
      expect(JSON.parse(String(init?.body))).toEqual({ espn_player_id: null });
    });
  });
});
