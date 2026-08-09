// Query hook for GET /api/teams/day-rings — the Topbar's day-of-week rings, computed
// from real scoring data (task 10.6). See
// backend/gridiron/services/fantasy_service.py's `day_rings` for the source of truth on
// the shape/semantics (one ring per user team per day, valued as that day's share of
// the team's week score).

import { useQuery } from "@tanstack/react-query";

import type { Envelope } from "../types/api";
import { apiClient } from "./client";

export interface DayRingValue {
  value: number;
  color: string;
}

export interface DayRing {
  letter: string;
  rings: DayRingValue[];
}

export interface DayRingsData {
  days: DayRing[];
  today_index: number | null;
}

const STALE_TIME_MS = 15_000;

export function useDayRings(week: number) {
  return useQuery({
    queryKey: ["day-rings", week],
    queryFn: () => apiClient.get<Envelope<DayRingsData>>(`/api/teams/day-rings?week=${week}`),
    staleTime: STALE_TIME_MS,
  });
}
