import { describe, expect, it } from "vitest";

import { parseTeamRoute, resolveTeamId, teamRoutePath } from "./teamRoute";

describe("parseTeamRoute", () => {
  it("reads the bare team route as the roster section", () => {
    expect(parseTeamRoute("/team/espn:l-1-t-2")).toEqual({
      teamId: "espn:l-1-t-2",
      section: "roster",
    });
  });

  it("reads the h2h and season sub-routes", () => {
    expect(parseTeamRoute("/team/espn:l-1-t-2/h2h")?.section).toBe("h2h");
    expect(parseTeamRoute("/team/espn:l-1-t-2/season")?.section).toBe("season");
  });

  it("returns null for non-team routes", () => {
    for (const path of ["/", "/gameday", "/settings", "/draft", "/team", "/team/"]) {
      expect(parseTeamRoute(path)).toBeNull();
    }
  });

  it("returns null for an unrecognized sub-route rather than guessing roster", () => {
    expect(parseTeamRoute("/team/espn:l-1-t-2/whatever")).toBeNull();
  });

  it("decodes a percent-encoded id so it matches what useParams yields", () => {
    // A copied/pasted URL can arrive with the colon encoded; the screens read the
    // decoded form off useParams, so an undecoded id here would never match a team.
    expect(parseTeamRoute("/team/espn%3Al-1-t-2/h2h")?.teamId).toBe("espn:l-1-t-2");
  });

  it("round-trips through teamRoutePath", () => {
    for (const section of ["roster", "h2h", "season"] as const) {
      const path = teamRoutePath("yahoo:l-9-t-3", section);
      expect(parseTeamRoute(path)).toEqual({ teamId: "yahoo:l-9-t-3", section });
    }
  });
});

describe("resolveTeamId", () => {
  const teams = [{ id: "espn:a" }, { id: "yahoo:b" }];

  it("prefers the remembered team over the first one", () => {
    expect(resolveTeamId("yahoo:b", teams)).toBe("yahoo:b");
  });

  it("falls back to the first team when nothing is remembered", () => {
    expect(resolveTeamId(null, teams)).toBe("espn:a");
  });

  it("drops a remembered id that is no longer in the league list", () => {
    // The persisted id outlives the league it names. Without this check, disconnecting
    // a league leaves a sidebar link to a team that no longer exists, and it survives
    // every reload because the id is in localStorage.
    expect(resolveTeamId("espn:disconnected", teams)).toBe("espn:a");
  });

  it("returns undefined when nothing is connected", () => {
    expect(resolveTeamId("espn:a", [])).toBeUndefined();
  });
});
