import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";

function stubFetch() {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ data: {}, meta: {} }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("apiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("bypasses the browser's HTTP cache", async () => {
    // The read endpoints answer with `Cache-Control: private, max-age=15`. Left to its
    // defaults the browser serves its own copy for those 15 seconds — including for the
    // refetch an SSE `data.changed` just asked for, which is the whole live-update path.
    // At the 10s tier that capped scores at 15-second quanta, 15 seconds behind the
    // server, with nothing on screen to suggest why.
    const fetchMock = stubFetch();

    await apiClient.get("/api/teams?week=2");

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.cache).toBe("no-store");
  });

  it("applies to writes too, not just reads", async () => {
    const fetchMock = stubFetch();

    await apiClient.post("/api/admin/refresh", { job: "refresh_fantasy" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.cache).toBe("no-store");
  });
});
