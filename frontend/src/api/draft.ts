// Query hooks + mutations for /api/draft* (task 3.7). See
// backend/gridiron/schemas/draft.py / backend/gridiron/api/draft.py for the source of
// truth on response shapes.
//
// Every query key here starts with "draft" so `events.ts`'s `queryKeyForScope("draft")
// -> ["draft"]` invalidates all of them by TanStack Query's prefix-match semantics —
// see that file's task 3.6 comment for why the prefix has to line up exactly.
//
// Mutations use optimistic updates (onMutate) so a mark-drafted / undo / set-current-pick
// tap feels instant on a phone during a live draft, with onError rollback to the
// snapshotted previous cache and an onSettled invalidation as the correctness backstop
// (the SSE `data.changed` event fired by the write path — services/differ.py's
// `draft_fingerprints` — will also invalidate, redundantly but harmlessly).
//
// Task 6.5 (design D12) — degraded-mode polling. `events.ts`'s app-wide SSE-down
// fallback only kicks in after a 30s-continuous disconnect and polls every 5 MINUTES
// (far too slow mid-draft), and it works by mutating `queryClient`'s default options —
// too blunt an instrument to special-case one screen without also slowing every other
// screen's fallback, or fighting events.ts for control of the same default. A per-query
// `refetchInterval` here is the safer mechanism (see the module-level comment in
// events.ts for why): it only affects these `["draft", ...]` queries, kicks in on ANY
// disconnect (not just a 30s-long one -- a live draft can't afford to wait that long),
// and needs no explicit teardown -- TanStack Query only schedules `refetchInterval`
// polls while a query has an active observer, and every draft query's only observers
// are components under screens/Draft, so it stops the instant the Draft screen unmounts.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useLiveConnectionStore } from "../stores/live";
import type { Envelope } from "../types/api";
import { apiClient } from "./client";

const STALE_TIME_MS = 15_000;
const DEGRADED_POLL_INTERVAL_MS = 5_000;

/** `false` (no interval) while SSE is connected -- normal invalidation-on-event
 * behavior applies, unchanged from before this task. Once disconnected, every draft
 * query polls every ~5s regardless of how long the disconnect has lasted. */
function useDraftRefetchInterval(): number | false {
  const connected = useLiveConnectionStore((s) => s.connected);
  return connected ? false : DEGRADED_POLL_INTERVAL_MS;
}

// ---------------------------------------------------------------------------
// Entity shapes (backend/gridiron/schemas/draft.py)
// ---------------------------------------------------------------------------

export interface CandidateOut {
  name: string;
  position: string;
  nfl_team: string | null;
  bye: number | null;
  adp_rank: number | null;
  overall_tier: number | null;
  positional_tier: number | null;
  risk_score: number | null;
  unpriced_risk: boolean;
  flags: string[];
}

export interface AnalystTakeOut {
  source: string;
  verified_accuracy: boolean;
  take: string;
  detail: string | null;
}

export interface BoardPlayerOut extends CandidateOut {
  id: number;
  adp: number | null;
  adp_round: number | null;
  risk: string | null;
  rookie: boolean;
  out_for_season: boolean;
  note: string | null;
  thesis: string | null;
  take_in_round: string | null;
  is_drafted: boolean;
  drafted_overall_pick: number | null;
  drafted_by_team: string | null;
  is_my_pick: boolean;
  // 6.3 -- full scouting content.
  sleeper_category: string | null;
  catalyst: string | null;
  format_fit: string | null;
  // Keyword-derived from note prose, NOT curated fact -- see PlayerDetail.tsx's
  // rendering, which labels these as a search aid, not a diagnosis.
  injury_tags: string[];
  analyst_takes: AnalystTakeOut[];
  overall_tier_label: string | null;
  positional_tier_label: string | null;
}

export interface BoardData {
  players: BoardPlayerOut[];
}

export interface PoolData {
  players: CandidateOut[];
}

export interface DraftPickOut {
  id: number;
  overall_pick: number;
  round: number | null;
  board_player_id: number | null;
  espn_player_id: number | null;
  player_name: string;
  position: string | null;
  drafted_by_team: string | null;
  is_my_pick: boolean;
  source: "manual" | "espn";
}

export interface RosterSlotOut {
  slot: string;
  position_group: string;
  filled: boolean;
  player: CandidateOut | null;
}

export interface ByeCollisionOut {
  bye: number;
  count: number;
  players: string[];
}

export interface RosterData {
  starters: RosterSlotOut[];
  bench: CandidateOut[];
  bye_collisions: ByeCollisionOut[];
}

export interface SettingsConflictOut {
  field: string;
  static_value: unknown;
  espn_value: unknown;
  resolved_value: unknown;
  confirmed_by_espn: boolean;
  note: string;
}

export interface DraftStateData {
  picks: DraftPickOut[];
  current_overall_pick: number;
  current_round: number;
  picks_until_next: number | null;
  my_upcoming_picks: number[];
  roster: RosterData;
  settings_conflicts: SettingsConflictOut[];
  session_status: string | null;
  league_teams: number;
  draft_over: boolean;
}

export interface RecommendationOut {
  candidate: CandidateOut;
  score: number;
  components: Record<string, number>;
  reason: string;
  fired_rule_ids: string[];
}

export interface TierAlarmOut {
  position: string;
  tier: number;
  remaining: number;
  picks_until_next: number;
}

export interface TurnPairOut {
  pick_a: number;
  pick_b: number;
  recommendation_a: RecommendationOut;
  recommendation_b: RecommendationOut;
}

export interface PositionalRunOut {
  position: string;
  count: number;
}

export interface RecommendationsData {
  current_overall_pick: number;
  picks_until_next: number | null;
  shortlist: RecommendationOut[];
  tier_alarms: TierAlarmOut[];
  bye_collisions: ByeCollisionOut[];
  positional_runs: PositionalRunOut[];
  advisories: string[];
  turn_pairs: TurnPairOut[];
}

export interface RecordPickInput {
  player_name?: string;
  board_player_id?: number;
  is_my_pick?: boolean;
  drafted_by_team?: string;
  overall_pick?: number;
}

export interface UndoResultData {
  undone: DraftPickOut | null;
}

export interface CurrentPickData {
  current_overall_pick: number;
  current_round: number;
  picks_until_next: number | null;
}

export interface SlotPlanTargetOut {
  name: string;
  group: string | null;
  sniped: boolean;
  drafted_by_me: boolean;
  drafted_by_team: string | null;
  still_available: boolean;
}

export interface SlotPlanEntryOut {
  picks: number[];
  label: string;
  confidence: string | null;
  rule: string | null;
  avoid: string[];
  targets: SlotPlanTargetOut[];
}

export interface SlotPlanData {
  applicable: boolean;
  user_draft_slot: number;
  structural_note: string | null;
  pick_numbers: number[];
  entries: SlotPlanEntryOut[];
  unplanned_pick_numbers: number[];
}

export interface EspnMatchCandidateOut {
  espn_player_id: number;
  full_name: string;
  position: string;
  nfl_team: string;
  is_dst: boolean;
}

export interface BoardMatchOut {
  board_player_name: string;
  espn_player_id: number | null;
  match_method: string;
  match_confidence: number;
  candidates: EspnMatchCandidateOut[];
}

export interface MatchesData {
  matches: BoardMatchOut[];
  method_counts: Record<string, number>;
  below_threshold_count: number;
}

// Confidence gate (task 4.5/4.6): a board entry below this needs human resolution
// before ESPN-live features (phase 5, not built yet) can be enabled. Must match
// backend/gridiron/services/draft_matches.py's CONFIDENCE_THRESHOLD.
export const MATCH_CONFIDENCE_THRESHOLD = 0.9;

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useDraftBoard() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "board"],
    queryFn: () => apiClient.get<Envelope<BoardData>>("/api/draft/board"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

export function useDraftPool() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "pool"],
    queryFn: () => apiClient.get<Envelope<PoolData>>("/api/draft/pool"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

export function useDraftState() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "state"],
    queryFn: () => apiClient.get<Envelope<DraftStateData>>("/api/draft/state"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

export function useDraftRecommendations() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "recommendations"],
    queryFn: () => apiClient.get<Envelope<RecommendationsData>>("/api/draft/recommendations"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

export function useDraftSlotPlan() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "slot-plan"],
    queryFn: () => apiClient.get<Envelope<SlotPlanData>>("/api/draft/slot-plan"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

export function useDraftMatches() {
  const refetchInterval = useDraftRefetchInterval();
  return useQuery({
    queryKey: ["draft", "matches"],
    queryFn: () => apiClient.get<Envelope<MatchesData>>("/api/draft/matches"),
    staleTime: STALE_TIME_MS,
    refetchInterval,
  });
}

// ---------------------------------------------------------------------------
// Mutations (optimistic)
// ---------------------------------------------------------------------------

/** Match a cached candidate/board row against a mark-drafted input. Callers always know
 * the player's name (BoardList/MarkDrafted read it straight off the row being tapped),
 * so name is the one reliable client-side key -- `board_player_id` is sent to the
 * backend for accuracy but pool rows (`CandidateOut`) don't carry an id to match on. */
function matchesInput(
  row: { name: string },
  boardPlayerId: number | null,
  input: RecordPickInput,
): boolean {
  if (input.board_player_id !== undefined) return boardPlayerId === input.board_player_id;
  return row.name === input.player_name;
}

export function useMarkDrafted() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RecordPickInput) => apiClient.post<DraftPickOut>("/api/draft/picks", input),
    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: ["draft"] });

      const previousPool = queryClient.getQueryData<Envelope<PoolData>>(["draft", "pool"]);
      const previousBoard = queryClient.getQueryData<Envelope<BoardData>>(["draft", "board"]);
      const previousState = queryClient.getQueryData<Envelope<DraftStateData>>(["draft", "state"]);

      if (previousPool) {
        queryClient.setQueryData<Envelope<PoolData>>(["draft", "pool"], {
          ...previousPool,
          data: {
            players: previousPool.data.players.filter((p) => p.name !== input.player_name),
          },
        });
      }

      if (previousBoard) {
        queryClient.setQueryData<Envelope<BoardData>>(["draft", "board"], {
          ...previousBoard,
          data: {
            players: previousBoard.data.players.map((p) =>
              matchesInput(p, p.id, input)
                ? {
                    ...p,
                    is_drafted: true,
                    // The backend assigns the real pick number when `overall_pick` is
                    // omitted (draft_state._next_unused_overall_pick), which is how
                    // MarkDrafted always calls this -- so there's no real number to
                    // optimistically show yet. Stay null (BoardList's PickNumber
                    // renders nothing for null) until onSettled's invalidation lands
                    // the server's answer, rather than fabricate one.
                    drafted_overall_pick: input.overall_pick ?? null,
                    drafted_by_team: input.drafted_by_team ?? null,
                    is_my_pick: input.is_my_pick ?? false,
                  }
                : p,
            ),
          },
        });
      }

      if (previousState) {
        queryClient.setQueryData<Envelope<DraftStateData>>(["draft", "state"], {
          ...previousState,
          data: {
            ...previousState.data,
            current_overall_pick: previousState.data.current_overall_pick + 1,
          },
        });
      }

      return { previousPool, previousBoard, previousState };
    },
    onError: (_err, _input, context) => {
      if (context?.previousPool) queryClient.setQueryData(["draft", "pool"], context.previousPool);
      if (context?.previousBoard)
        queryClient.setQueryData(["draft", "board"], context.previousBoard);
      if (context?.previousState)
        queryClient.setQueryData(["draft", "state"], context.previousState);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["draft"] });
    },
  });
}

export function useUndoLastPick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.delete<UndoResultData>("/api/draft/picks/last"),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["draft"] });

      const previousState = queryClient.getQueryData<Envelope<DraftStateData>>(["draft", "state"]);
      const previousBoard = queryClient.getQueryData<Envelope<BoardData>>(["draft", "board"]);

      if (previousState && previousState.data.picks.length > 0) {
        const picks = previousState.data.picks;
        const lastPick = picks[picks.length - 1];

        queryClient.setQueryData<Envelope<DraftStateData>>(["draft", "state"], {
          ...previousState,
          data: {
            ...previousState.data,
            picks: picks.slice(0, -1),
            current_overall_pick: Math.max(previousState.data.current_overall_pick - 1, 1),
          },
        });

        if (previousBoard) {
          queryClient.setQueryData<Envelope<BoardData>>(["draft", "board"], {
            ...previousBoard,
            data: {
              players: previousBoard.data.players.map((p) =>
                p.drafted_overall_pick === lastPick.overall_pick
                  ? {
                      ...p,
                      is_drafted: false,
                      drafted_overall_pick: null,
                      drafted_by_team: null,
                      is_my_pick: false,
                    }
                  : p,
              ),
            },
          });
        }
      }

      return { previousState, previousBoard };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousState)
        queryClient.setQueryData(["draft", "state"], context.previousState);
      if (context?.previousBoard)
        queryClient.setQueryData(["draft", "board"], context.previousBoard);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["draft"] });
    },
  });
}

export function useSetCurrentPick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (overallPick: number) =>
      apiClient.put<CurrentPickData>("/api/draft/current-pick", { overall_pick: overallPick }),
    onMutate: async (overallPick) => {
      await queryClient.cancelQueries({ queryKey: ["draft", "state"] });
      const previousState = queryClient.getQueryData<Envelope<DraftStateData>>(["draft", "state"]);
      if (previousState) {
        queryClient.setQueryData<Envelope<DraftStateData>>(["draft", "state"], {
          ...previousState,
          data: { ...previousState.data, current_overall_pick: overallPick },
        });
      }
      return { previousState };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousState)
        queryClient.setQueryData(["draft", "state"], context.previousState);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["draft"] });
    },
  });
}

export interface MatchOverrideInput {
  boardPlayerName: string;
  espnPlayerId: number | null;
}

// Task 4.6 -- resolving a match (or recording "no ESPN match") from MatchResolution.tsx.
// No optimistic patch: this is a low-frequency, deliberate action (not a burst-entry
// tap during a live draft like MarkDrafted), so a plain invalidate-on-settle is simpler
// and correct without extra machinery.
export function useSetMatchOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ boardPlayerName, espnPlayerId }: MatchOverrideInput) =>
      apiClient.post<BoardMatchOut>(`/api/draft/matches/${encodeURIComponent(boardPlayerName)}`, {
        espn_player_id: espnPlayerId,
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["draft"] });
    },
  });
}
