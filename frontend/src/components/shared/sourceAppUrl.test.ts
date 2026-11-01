import { describe, expect, it } from "vitest";

import { sourceAppLink } from "./sourceAppUrl";

describe("sourceAppLink", () => {
  it("sends an ESPN team to its team page, which ESPN's app claims as a universal link", () => {
    expect(sourceAppLink("espn:l-1234567-t-8")).toEqual({
      platform: "espn",
      label: "ESPN",
      url: "https://fantasy.espn.com/football/team?leagueId=1234567&teamId=8",
    });
  });

  it("sends a Yahoo team to /f1/{league}/{team}, the path Yahoo's app claims", () => {
    expect(sourceAppLink("yahoo:461.l.98765.t.4")).toEqual({
      platform: "yahoo",
      label: "Yahoo",
      url: "https://football.fantasysports.yahoo.com/f1/98765/4",
    });
  });

  it("accepts Yahoo's code-style game key as well as the numeric one", () => {
    expect(sourceAppLink("yahoo:nfl.l.123456.t.10")?.url).toBe(
      "https://football.fantasysports.yahoo.com/f1/123456/10",
    );
  });

  it.each([
    ["an unknown platform", "sleeper:abc"],
    ["a league id rather than a team id", "yahoo:461.l.98765"],
    ["an ESPN league id", "espn:1234567"],
    ["an id that only looks Yahoo-shaped", "yahoo:l-9-t-3"],
    ["an empty id", ""],
  ])("returns null for %s", (_label, id) => {
    expect(sourceAppLink(id)).toBeNull();
  });
});
