import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHighlightStore } from "../stores/highlights";
import { describePlay, pullHighlights, type PlayerHighlight } from "./highlights";

const CURSOR_KEY = "gridiron.highlights.cursor";

function highlight(id: number): PlayerHighlight {
  return {
    id,
    kind: "touchdown",
    stat_key: "rush_td",
    yards: 12,
    stat_line: "14 car · 71 yds · 1 TD",
    player_id: "yahoo:p1",
    player_name: "Bijan Robinson",
    position: "RB",
    nfl_team: "ATL",
    headshot_url: "/api/headshots/yahoo/1.png",
    created_at: "2026-10-25T18:00:00",
  };
}

function stubFetch(data: { highlights: PlayerHighlight[]; latest_id: number | null }) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<unknown>>(async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ data, meta: {} }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("pullHighlights", () => {
  beforeEach(() => {
    localStorage.clear();
    useHighlightStore.setState({ queue: [], overflow: 0 });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("seeds the cursor on a first load without playing anything", async () => {
    const fetchMock = stubFetch({ highlights: [], latest_id: 7 });

    await pullHighlights();

    expect(fetchMock.mock.calls[0]![0]).toBe("/api/highlights");
    expect(localStorage.getItem(CURSOR_KEY)).toBe("7");
    expect(useHighlightStore.getState().queue).toEqual([]);
  });

  it("asks after the cursor, queues what's new, and advances to latest_id", async () => {
    localStorage.setItem(CURSOR_KEY, "7");
    const fetchMock = stubFetch({ highlights: [highlight(8)], latest_id: 9 });

    await pullHighlights();

    expect(fetchMock.mock.calls[0]![0]).toBe("/api/highlights?after=7");
    expect(useHighlightStore.getState().queue.map((h) => h.id)).toEqual([8]);
    expect(localStorage.getItem(CURSOR_KEY)).toBe("9");
  });

  it("seeds 0 on an empty table so the first highlight ever still plays", async () => {
    stubFetch({ highlights: [], latest_id: null });
    await pullHighlights();
    expect(localStorage.getItem(CURSOR_KEY)).toBe("0");

    const fetchMock = stubFetch({ highlights: [highlight(1)], latest_id: 1 });
    await pullHighlights();

    expect(fetchMock.mock.calls[0]![0]).toBe("/api/highlights?after=0");
    expect(useHighlightStore.getState().queue.map((h) => h.id)).toEqual([1]);
  });
});

describe("highlight queue", () => {
  beforeEach(() => {
    useHighlightStore.setState({ queue: [], overflow: 0 });
  });

  it("caps the line and counts the rest as overflow until it drains", () => {
    const { enqueue, shift } = useHighlightStore.getState();
    enqueue([1, 2, 3, 4, 5].map(highlight));

    expect(useHighlightStore.getState().queue.map((h) => h.id)).toEqual([1, 2, 3]);
    expect(useHighlightStore.getState().overflow).toBe(2);

    shift();
    shift();
    shift();
    expect(useHighlightStore.getState()).toMatchObject({ queue: [], overflow: 0 });
  });

  it("ignores a highlight already in line", () => {
    const { enqueue } = useHighlightStore.getState();
    enqueue([highlight(1)]);
    enqueue([highlight(1), highlight(2)]);

    expect(useHighlightStore.getState().queue.map((h) => h.id)).toEqual([1, 2]);
  });
});

describe("describePlay", () => {
  it("leads with the yards when the feed has them", () => {
    expect(describePlay({ stat_key: "rush_td", yards: 34 })).toBe("34-yd rushing TD");
    expect(describePlay({ stat_key: "rec_40p", yards: 57 })).toBe("57-yd catch");
  });

  it("falls back without yards", () => {
    expect(describePlay({ stat_key: "rec_td", yards: null })).toBe("Receiving TD");
    expect(describePlay({ stat_key: "rush_40p", yards: null })).toBe("40+ yd run");
  });
});
