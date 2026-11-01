import { describe, expect, it } from "vitest";

import {
  DEFAULT_WAIVER_FILTERS,
  activeFilterCount,
  describeFilters,
  formatGameDay,
  formatShortDate,
  sheetFiltersOf,
  statusOptionId,
  statusOptions,
  toQueryOptions,
} from "./filters";

const defaults = sheetFiltersOf(DEFAULT_WAIVER_FILTERS);

describe("waiver filters", () => {
  it("lists Yahoo's status options with one row per remaining game day", () => {
    const options = statusOptions(["2026-11-05", "2026-11-08", "2026-11-09"]);

    expect(options.map((o) => o.label)).toEqual([
      "All Available",
      "All Available (Games Thursday - 11/5)",
      "All Available (Games Sunday - 11/8)",
      "All Available (Games Monday - 11/9)",
      "Free Agents Only",
      "Waivers Only",
      "All Players",
    ]);
    expect(options[1]).toMatchObject({ status: "available", gameDay: "2026-11-05" });
  });

  it("reads a YYYY-MM-DD as a calendar day, not as UTC midnight", () => {
    // `new Date("2026-11-05")` is the evening of the 4th anywhere in the US.
    expect(formatGameDay("2026-11-05")).toBe("Thursday - 11/5");
    expect(formatShortDate("2026-11-04")).toBe("11/4");
  });

  it("counts each sheet choice once, whatever the status list picked", () => {
    expect(activeFilterCount(defaults)).toBe(0);
    expect(activeFilterCount({ ...defaults, status: "waivers" })).toBe(1);
    expect(activeFilterCount({ ...defaults, gameDay: "2026-11-05" })).toBe(1);
    expect(activeFilterCount({ ...defaults, status: "all", showMine: true, sort: "owned" })).toBe(
      3,
    );
  });

  it("identifies the chosen status row by game day first", () => {
    expect(statusOptionId({ status: "available", gameDay: "2026-11-08" })).toBe("day:2026-11-08");
    expect(statusOptionId({ status: "free_agents", gameDay: null })).toBe("free_agents");
  });

  it("describes a filtered list in one line, and says nothing at the defaults", () => {
    expect(describeFilters(defaults)).toBeNull();
    expect(describeFilters({ ...defaults, status: "waivers", showMine: true })).toBe(
      "Waivers Only · Showing my team",
    );
    expect(describeFilters({ ...defaults, gameDay: "2026-11-05", sort: "upgrade_week" })).toBe(
      "Playing Thursday · By upgrade (this week)",
    );
  });

  it("maps the sheet onto the endpoint's options", () => {
    expect(toQueryOptions({ status: "all", gameDay: null, showMine: true, sort: "owned" })).toEqual(
      { status: "all", includeMine: true, gameDay: null, sort: "owned" },
    );
  });
});
