// Screen 6: Game Day — every matchup at once, arranged once and then left alone.
//
// The Sunday mode this screen exists for is full-screen, read from across the room,
// unattended for hours. Two consequences run through the whole file:
//
//   - Interaction is for SETUP, not for reading. Nothing here needs to be clicked for
//     the screen to be fully informative; the roster reveals itself by panel width
//     (design D3), not by a disclosure the user has to remember to open.
//   - Layout is persisted. A wall display that forgets its arrangement on restart is
//     one nobody sets up twice, and the LaunchAgent restarts this app.
//
// All data comes from ONE query (design D5). No panel fetches anything.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useGameDay } from "../../api/teams";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore, type GameDayMode, type GameDaySortMode } from "../../stores/ui";
import type { GameDayMatchup } from "../../types/api";
import "../../styles/gameday.css";
import { applySort, liveCount, reconcileOrder, reorder } from "./arrangement";
import { GameDayPanel } from "./GameDayPanel";
import { GameDaySkeleton } from "./GameDaySkeleton";

const MODES: { id: GameDayMode; label: string }[] = [
  { id: "g2", label: "2-across" },
  { id: "g3", label: "3-across" },
  { id: "c4", label: "4-column" },
  { id: "spot", label: "Spotlight" },
];

const SORTS: { id: GameDaySortMode; label: string }[] = [
  { id: "manual", label: "Manual" },
  { id: "margin", label: "Closest" },
  { id: "live", label: "Most live" },
];

export default function GameDay() {
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();
  const gameDayQuery = useGameDay(week);
  const platformsDisconnected = usePlatformsDisconnected(gameDayQuery.data?.meta);

  const layout = useUiStore((s) => s.gameDay);
  const setMode = useUiStore((s) => s.setGameDayMode);
  const setOrder = useUiStore((s) => s.setGameDayOrder);
  const setSpan = useUiStore((s) => s.setGameDaySpan);
  const setOpenIds = useUiStore((s) => s.setGameDayOpenIds);
  const setShutIds = useUiStore((s) => s.setGameDayShutIds);
  const setRosterOverride = useUiStore((s) => s.setGameDayRosterOverride);
  const setSortMode = useUiStore((s) => s.setGameDaySortMode);

  const [spotlightId, setSpotlightId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);

  const matchups = useMemo(() => gameDayQuery.data?.data.matchups ?? [], [gameDayQuery.data]);
  const byId = useMemo(
    () => Object.fromEntries(matchups.map((m) => [m.team_id, m])) as Record<string, GameDayMatchup>,
    [matchups],
  );

  // Reconciled on every read, not on write: the persisted order can name teams that
  // have since been disconnected AND miss teams connected since it was stored, and only
  // handling the first half would make a newly connected league's panel invisible
  // (design D8).
  const visibleIds = useMemo(() => {
    const reconciled = reconcileOrder(
      layout.order,
      matchups.map((m) => m.team_id),
    );
    return applySort(reconciled, byId, layout.sortMode);
  }, [layout.order, layout.sortMode, matchups, byId]);

  // Escape closes the spotlight. Bound at the document so it works regardless of what
  // holds focus inside the overlay.
  useEffect(() => {
    if (spotlightId === null) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setSpotlightId(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [spotlightId]);

  // The panel resolves the direction from the roster's real rendered visibility, so
  // this just records the choice — see GameDayPanel's handleToggleRoster.
  const toggleRoster = useCallback(
    (id: string, next: "open" | "shut") => setRosterOverride(id, next),
    [setRosterOverride],
  );

  const handleDrop = useCallback(
    (targetId: string) => {
      if (dragId === null) return;
      setOrder(reorder(visibleIds, dragId, targetId));
      // A hand-placed order and an auto-sort mode are mutually exclusive states, not
      // layers — so completing a drag drops back to manual rather than letting the next
      // sort pass undo the user's placement (design D8).
      setSortMode("manual");
      setDragId(null);
    },
    [dragId, visibleIds, setOrder, setSortMode],
  );

  const cycleSpan = useCallback(
    (id: string) => {
      // Pointer-drag resize on a CSS grid resolves to a small set of discrete spans, so
      // the handle cycles 1x1 -> 2x1 -> 2x2 -> 1x1 rather than tracking pixels into a
      // continuous size the grid would only snap back anyway.
      const current = layout.spans[id] ?? { cols: 1 as const, rows: 1 as const };
      const next =
        current.cols === 1
          ? { cols: 2 as const, rows: 1 as const }
          : current.rows === 1
            ? { cols: 2 as const, rows: 2 as const }
            : { cols: 1 as const, rows: 1 as const };
      setSpan(id, next);
    },
    [layout.spans, setSpan],
  );

  const rosterOverrideFor = (id: string): "open" | "shut" | undefined => {
    // Absent when the user has expressed no preference, so the container query decides.
    // An attribute selector cannot match a missing attribute, which is exactly the
    // fall-through wanted (design D3).
    if (layout.openIds.includes(id)) return "open";
    if (layout.shutIds.includes(id)) return "shut";
    return undefined;
  };

  if (platformsDisconnected) {
    return <EmptyState testId="gameday-empty" />;
  }

  if (gameDayQuery.isError) {
    return (
      <>
        <GameDayHeader matchups={[]} week={week} />
        <ErrorCard
          error={gameDayQuery.error}
          fallbackMessage="Couldn't load today's matchups."
          onRetry={() => void queryClient.invalidateQueries({ queryKey: ["gameday"] })}
          testId="gameday-error"
        />
      </>
    );
  }

  if (gameDayQuery.isLoading || !gameDayQuery.data) {
    return (
      <>
        <GameDayHeader matchups={[]} week={week} />
        <GameDaySkeleton mode={layout.mode} />
      </>
    );
  }

  const spotlit = spotlightId !== null ? byId[spotlightId] : undefined;

  return (
    <>
      <GameDayHeader matchups={matchups} week={week} />

      <div className="gd-controls" data-testid="gameday-controls">
        <div className="gd-seg" role="group" aria-label="Arrangement">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={"gd-seg-btn" + (layout.mode === m.id ? " active" : "")}
              aria-pressed={layout.mode === m.id}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="gd-seg" role="group" aria-label="Sort">
          {SORTS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={"gd-seg-btn" + (layout.sortMode === s.id ? " active" : "")}
              aria-pressed={layout.sortMode === s.id}
              onClick={() => setSortMode(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="gd-controls-spacer" />

        <button
          type="button"
          className="gd-seg-btn"
          onClick={() => {
            setOpenIds(matchups.map((m) => m.team_id));
            setShutIds([]);
          }}
        >
          Expand all
        </button>
        <button
          type="button"
          className="gd-seg-btn"
          onClick={() => {
            // Collapse all is an explicit shut, not a clearing of preferences —
            // otherwise wide panels would fall back to the query and stay open.
            setOpenIds([]);
            setShutIds(matchups.map((m) => m.team_id));
          }}
        >
          Collapse all
        </button>
      </div>

      <div className="gd-stage" data-layout={layout.mode} data-testid="gameday-stage">
        {visibleIds.map((id) => {
          const matchup = byId[id];
          if (!matchup) return null;
          return (
            <GameDayPanel
              key={id}
              matchup={matchup}
              span={layout.spans[id]}
              rosterOverride={rosterOverrideFor(id)}
              onToggleRoster={(next) => toggleRoster(id, next)}
              onSpotlight={() => setSpotlightId(id)}
              onHeaderDragStart={() => setDragId(id)}
              onHeaderDragOver={(event) => event.preventDefault()}
              onHeaderDrop={() => handleDrop(id)}
              onResizePointerDown={() => cycleSpan(id)}
            />
          );
        })}
      </div>

      {spotlit && (
        <div
          className="gd-spotlight-backdrop"
          data-testid="gameday-spotlight"
          role="presentation"
          onClick={() => setSpotlightId(null)}
        >
          <div className="gd-spotlight-frame" onClick={(event) => event.stopPropagation()}>
            <GameDayPanel
              matchup={spotlit}
              isSpotlight
              // Spotlight always shows the roster, whatever the panel's own override was
              // on the stage — it is the one place with room for it unconditionally.
              rosterOverride="open"
              onSpotlight={() => setSpotlightId(null)}
            />
          </div>
        </div>
      )}
    </>
  );
}

function GameDayHeader({ matchups, week }: { matchups: GameDayMatchup[]; week: number }) {
  const leading = matchups.filter((m) => m.score > m.opp_score).length;
  const live = matchups.reduce((total, m) => total + liveCount(m), 0);

  return (
    <>
      <h1 className="large-title">Game Day</h1>
      <p className="large-subtitle">
        Week {week} · {matchups.length} {matchups.length === 1 ? "matchup" : "matchups"} ·{" "}
        <span style={{ color: "var(--move)" }}>{leading} leading</span>
        {live > 0 && (
          <>
            {" · "}
            <span style={{ color: "var(--live)" }}>{live} live</span>
          </>
        )}
      </p>
    </>
  );
}
