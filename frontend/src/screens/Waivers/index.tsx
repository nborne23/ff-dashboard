// Screen 7: Waivers — the free-agent/waiver pool for one team's league, ranked by
// how much each candidate would upgrade the lineup.
//
// Team-scoped, like Matchups and Season, because the pool is a property of one
// league: availability and projections both differ between leagues, so there is no
// cross-league pool to show.
//
// The ranking is by `delta_vs_worst_starter`, not by raw projection. That distinction
// is the screen's whole value: ordered by season projection, real data returns eight
// consecutive quarterbacks, every one of them worse than the QB already started.

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { useTeam, useWaivers } from "../../api/teams";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { WaiverTable } from "./WaiverTable";
import { WaiversSkeleton } from "./WaiversSkeleton";

const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const;

export default function Waivers() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();
  const [position, setPosition] = useState<string | undefined>(undefined);

  const teamQuery = useTeam(teamId, week);
  const waiversQuery = useWaivers(teamId, week, position);
  const platformsDisconnected = usePlatformsDisconnected(teamQuery.data?.meta);

  const retry = () => void queryClient.invalidateQueries({ queryKey: ["waivers", teamId] });

  if (platformsDisconnected) {
    return <EmptyState testId="waivers-empty" />;
  }

  if (waiversQuery.isError || teamQuery.isError) {
    return (
      <ErrorCard
        error={waiversQuery.error ?? teamQuery.error}
        fallbackMessage="Couldn't load available players."
        onRetry={retry}
        testId="waivers-error"
      />
    );
  }

  // Only the first load shows the skeleton. A position change refetches, and swapping
  // the whole table for a skeleton on every filter click makes the control feel like
  // it is reloading the page rather than narrowing a list.
  if (waiversQuery.isLoading || !waiversQuery.data) {
    return <WaiversSkeleton />;
  }

  const team = teamQuery.data?.data.team;
  const { candidates } = waiversQuery.data.data;

  return (
    <>
      <h1 className="large-title">Waivers</h1>
      <p className="large-subtitle">
        {team ? `${team.name} · ` : ""}Ranked by upgrade over your weakest eligible starter
      </p>

      <div
        style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}
        role="group"
        aria-label="Filter by position"
      >
        <button
          type="button"
          className={"pill" + (position === undefined ? " active" : "")}
          aria-pressed={position === undefined}
          onClick={() => setPosition(undefined)}
        >
          All
        </button>
        {POSITIONS.map((p) => (
          <button
            key={p}
            type="button"
            className={"pill" + (position === p ? " active" : "")}
            aria-pressed={position === p}
            onClick={() => setPosition(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <WaiverTable candidates={candidates} />
    </>
  );
}
