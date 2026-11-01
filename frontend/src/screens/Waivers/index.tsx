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
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useTeam, useWaivers } from "../../api/teams";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { useWaiverFilters } from "../../stores/waiverFilters";
import "../../styles/waivers.css";
import { activeFilterCount, describeFilters, sheetFiltersOf, toQueryOptions } from "./filters";
import { WaiverFilterSheet } from "./WaiverFilterSheet";
import { WaiverTable } from "./WaiverTable";
import { WaiversSkeleton } from "./WaiversSkeleton";

/** Sliders glyph for the Filters button — SF Symbols' `slider.horizontal.3` shape. */
function FilterGlyph() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="10" cy="12" r="2" />
      <circle cx="18" cy="18" r="2" />
    </svg>
  );
}

const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const;

export default function Waivers() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();
  // Position and the sheet's choices are remembered per team for the session, so
  // hopping to another team's waivers and back doesn't throw the filters away.
  const [filters, setFilters] = useWaiverFilters(teamId);
  const position = filters.position ?? undefined;
  const sheetFilters = sheetFiltersOf(filters);
  const [sheetOpen, setSheetOpen] = useState(false);

  const teamQuery = useTeam(teamId, week);
  const waiversQuery = useWaivers(teamId, week, position, toQueryOptions(sheetFilters));
  const platformsDisconnected = usePlatformsDisconnected(teamQuery.data?.meta);

  // A remembered game day the server no longer honors (its games have all finished, or
  // the week changed) is dropped here, so the sheet and the subtitle stop claiming a
  // filter the list isn't under. Never on placeholder data: while a new filter's request
  // is in flight, the previous page — which didn't ask for that day — is still showing.
  const appliedDay = waiversQuery.data?.data.game_day ?? null;
  const settled = Boolean(waiversQuery.data) && !waiversQuery.isPlaceholderData;
  useEffect(() => {
    if (settled && filters.gameDay !== null && appliedDay === null) {
      setFilters({ gameDay: null });
    }
  }, [settled, filters.gameDay, appliedDay, setFilters]);

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
  const { candidates, game_days: gameDays = [] } = waiversQuery.data.data;
  const activeCount = activeFilterCount(sheetFilters);
  const summary = describeFilters(sheetFilters);

  return (
    <>
      <div className="waivers-header">
        <h1 className="large-title">Waivers</h1>
        <button
          type="button"
          className={"btn waiver-filter-trigger" + (activeCount > 0 ? " active" : "")}
          aria-haspopup="dialog"
          aria-label={activeCount > 0 ? `Filters, ${activeCount} active` : "Filters"}
          onClick={() => setSheetOpen(true)}
        >
          <FilterGlyph />
          Filters
          {activeCount > 0 && (
            <span className="waiver-filter-count" aria-hidden="true">
              {activeCount}
            </span>
          )}
        </button>
      </div>
      <p className="large-subtitle">
        {team ? `${team.name} · ` : ""}
        {summary ?? "Ranked by upgrade over your weakest eligible starter"}
      </p>

      {/* A segmented control, not a row of chips: the options are mutually exclusive
          and exactly one is always selected, which is what a segmented control says. */}
      <div className="segmented segmented-fill" role="group" aria-label="Filter by position">
        <button
          type="button"
          className={position === undefined ? "active" : ""}
          aria-pressed={position === undefined}
          onClick={() => setFilters({ position: null })}
        >
          All
        </button>
        {POSITIONS.map((p) => (
          <button
            key={p}
            type="button"
            className={position === p ? "active" : ""}
            aria-pressed={position === p}
            onClick={() => setFilters({ position: p })}
          >
            {p}
          </button>
        ))}
      </div>

      <WaiverTable candidates={candidates} />

      {sheetOpen && (
        <WaiverFilterSheet
          filters={sheetFilters}
          gameDays={gameDays}
          onClose={() => setSheetOpen(false)}
          onApply={(next) => {
            setFilters(next);
            setSheetOpen(false);
          }}
        />
      )}
    </>
  );
}
