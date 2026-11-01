// The Waivers filter sheet's vocabulary: what can be chosen, what it is called, and how
// it maps onto `useWaivers`' server-side options.
//
// Modeled on Yahoo's filter sheet, adapted from basketball's daily slate to the NFL's
// Thursday / Sunday / Monday one: Yahoo offers "All Available (Games Tuesday - 10/27)",
// this offers the same for each day this week with a game still to play.

import type { WaiverQueryOptions } from "../../api/teams";

export type WaiverStatus = NonNullable<WaiverQueryOptions["status"]>;
export type WaiverSort = NonNullable<WaiverQueryOptions["sort"]>;

/** Everything the Waivers screen filters on, per team. `position` is the segmented
 *  control above the table; the rest live in the sheet. */
export interface WaiverFilters {
  position: string | null;
  status: WaiverStatus;
  /** `YYYY-MM-DD`; only meaningful with status "available", as in Yahoo's list. */
  gameDay: string | null;
  showMine: boolean;
  sort: WaiverSort;
}

export const DEFAULT_WAIVER_FILTERS: WaiverFilters = {
  position: null,
  status: "available",
  gameDay: null,
  showMine: false,
  sort: "upgrade",
};

/** The sheet's own choices, without the position the segmented control already shows. */
export type SheetFilters = Omit<WaiverFilters, "position">;

export function sheetFiltersOf(filters: WaiverFilters): SheetFilters {
  return {
    status: filters.status,
    gameDay: filters.gameDay,
    showMine: filters.showMine,
    sort: filters.sort,
  };
}

/** How many sheet choices differ from the defaults — the trigger button's badge. The
 *  status list is one choice whether it picked a status or a game day. */
export function activeFilterCount(filters: SheetFilters): number {
  return (
    Number(filters.status !== "available" || filters.gameDay !== null) +
    Number(filters.showMine) +
    Number(filters.sort !== "upgrade")
  );
}

export interface StatusOption {
  id: string;
  label: string;
  status: WaiverStatus;
  gameDay: string | null;
}

export function statusOptionId(filters: Pick<SheetFilters, "status" | "gameDay">): string {
  return filters.gameDay ? `day:${filters.gameDay}` : filters.status;
}

/** Yahoo's STATUS list, with one "All Available (Games …)" row per remaining game day. */
export function statusOptions(gameDays: string[]): StatusOption[] {
  return [
    { id: "available", label: "All Available", status: "available", gameDay: null },
    ...gameDays.map((day) => ({
      id: `day:${day}`,
      label: `All Available (Games ${formatGameDay(day)})`,
      status: "available" as const,
      gameDay: day,
    })),
    { id: "free_agents", label: "Free Agents Only", status: "free_agents", gameDay: null },
    { id: "waivers", label: "Waivers Only", status: "waivers", gameDay: null },
    { id: "all", label: "All Players", status: "all", gameDay: null },
  ];
}

export const SORT_OPTIONS: Array<{ id: WaiverSort; label: string; detail: string }> = [
  { id: "upgrade", label: "Upgrade", detail: "Rest of season" },
  { id: "upgrade_week", label: "Upgrade", detail: "This week" },
  { id: "owned", label: "% Rostered", detail: "Across all leagues" },
];

/** A `YYYY-MM-DD` as a local calendar date. `new Date("2026-11-05")` would parse it as
 *  UTC midnight — the evening of the 4th everywhere in the US. */
export function parseCalendarDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** "Thursday - 11/5", Yahoo's format for a game-day option. */
export function formatGameDay(iso: string): string {
  const date = parseCalendarDate(iso);
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  return `${weekday} - ${date.getMonth() + 1}/${date.getDate()}`;
}

/** "11/4", for the "Waivers (clears 11/4)" row badge. */
export function formatShortDate(iso: string): string {
  const date = parseCalendarDate(iso);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** The sheet's choices as `useWaivers` options. */
export function toQueryOptions(filters: SheetFilters): WaiverQueryOptions {
  return {
    status: filters.status,
    includeMine: filters.showMine,
    gameDay: filters.gameDay,
    sort: filters.sort,
  };
}

/** One line under the title saying what the list is, so a filtered list never reads as
 *  the whole pool. Null at the defaults. */
export function describeFilters(filters: SheetFilters): string | null {
  const parts: string[] = [];
  if (filters.gameDay) {
    parts.push(`Playing ${formatGameDay(filters.gameDay).split(" - ")[0]}`);
  } else if (filters.status !== "available") {
    parts.push(statusOptions([]).find((o) => o.id === filters.status)?.label ?? filters.status);
  }
  if (filters.showMine) parts.push("Showing my team");
  if (filters.sort !== "upgrade") {
    const sort = SORT_OPTIONS.find((o) => o.id === filters.sort);
    if (sort) parts.push(`By ${sort.label.toLowerCase()} (${sort.detail.toLowerCase()})`);
  }
  return parts.length ? parts.join(" · ") : null;
}
