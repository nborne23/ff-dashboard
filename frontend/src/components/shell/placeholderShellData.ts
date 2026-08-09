/**
 * PLACEHOLDER MODULE — remove once the Sidebar's "My Teams" flyout gets a real team
 * list source (today it's `useTeams()`'s week-scoped list, which the always-visible
 * shell can't depend on without adding a fetch dependency the flyout doesn't otherwise
 * need). Topbar's DayRings used to live here too, but task 10.6 wired it to real data
 * (api/dayRings.ts) — this file now only covers the still-placeholder team list.
 */

export interface PlaceholderTeam {
  id: string;
  name: string;
  platform: "yahoo" | "espn";
}

export const PLACEHOLDER_TEAMS: PlaceholderTeam[] = [
  { id: "yhb", name: "Highland Bombers", platform: "yahoo" },
  { id: "ele", name: "Eleven Thunder", platform: "espn" },
  { id: "ach", name: "Achilles Heels", platform: "espn" },
  { id: "byd", name: "Bayside Tigers", platform: "yahoo" },
  { id: "rvr", name: "River Phantoms", platform: "yahoo" },
  { id: "stl", name: "Stallion 6", platform: "espn" },
];
