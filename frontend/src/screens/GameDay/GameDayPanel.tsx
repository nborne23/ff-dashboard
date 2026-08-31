// One Game Day panel: the complete head-to-head for a single matchup (design D1).
//
// Fixed vertical order — meta row, score row, stat strip, disclosure, mirrored roster.
// Everything below the meta row is a function of the envelope entry alone; the panel
// issues no request of its own.

import { TeamLogo } from "../../components/shared/TeamLogo";
import { useRef, type PointerEvent as ReactPointerEvent } from "react";

import type { GameDayMatchup } from "../../types/api";
import { computeProjectedFinal } from "../HeadToHead/projectedFinal";
import { liveCount } from "./arrangement";
import { MirroredRoster } from "./MirroredRoster";
import { TIE_EPSILON, useLeadFlip } from "./useLeadFlip";

export interface GameDayPanelProps {
  matchup: GameDayMatchup;
  /**
   * Manual disclosure override, or `undefined` to let the container query decide.
   * Deliberately three-valued: "the user has not expressed a preference" is a distinct
   * state from "the user shut it", and only the first defers to the width (design D3).
   */
  rosterOverride?: "open" | "shut";
  /**
   * Called with the state the roster should move TO, derived from whether it is
   * currently rendered. The panel resolves that itself because only CSS knows: the
   * container query, not React, decides the default at a given width.
   */
  onToggleRoster?: (next: "open" | "shut") => void;
  onSpotlight?: () => void;
  /** Spotlight renders the panel alone in an overlay, at its widest density. */
  isSpotlight?: boolean;
  span?: { cols: 1 | 2; rows: 1 | 2 };
  /** Reorder is bound to the header only — never the body (design, gesture collision). */
  onHeaderDragStart?: () => void;
  onHeaderDragOver?: (event: React.DragEvent) => void;
  onHeaderDrop?: () => void;
  /** Resize is bound to the corner handle only. */
  onResizePointerDown?: (event: ReactPointerEvent) => void;
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

export function GameDayPanel({
  matchup,
  rosterOverride,
  onToggleRoster,
  onSpotlight,
  isSpotlight = false,
  span,
  onHeaderDragStart,
  onHeaderDragOver,
  onHeaderDrop,
  onResizePointerDown,
}: GameDayPanelProps) {
  const rosterRef = useRef<HTMLDivElement>(null);

  /**
   * Read the roster's real rendered visibility at click time and ask for the opposite.
   *
   * This is a single synchronous read on a user gesture — not the per-panel
   * `ResizeObserver` feeding React state that design D3 rejects. Nothing observes,
   * nothing re-renders on resize, and the density ladder still lives only in CSS. It is
   * simply the only way for the handler to know which direction "toggle" means, since
   * below 540px the default is closed and at or above it the default is open.
   */
  const handleToggleRoster = () => {
    if (!onToggleRoster) return;
    const node = rosterRef.current;
    const visible = node !== null && getComputedStyle(node).display !== "none";
    onToggleRoster(visible ? "shut" : "open");
  };

  const margin = matchup.score - matchup.opp_score;
  const tied = Math.abs(margin) < TIE_EPSILON;
  const leadFlip = useLeadFlip(margin);

  // --- Panel state derives from authoritative fields only (design D4) ---------------
  //
  // `is_live` off the slots and `is_complete` off the matchup. NOT a `game_state`
  // comparison: discovery writes roster rows with a null `game_state`, so "every slot
  // is post" is permanently false for them and a panel derived that way would never
  // dim — the single most load-bearing cue on the screen.
  const live = liveCount(matchup);
  const isLive = live > 0;
  const isSettled = matchup.is_complete;

  // Game Day reads the TRUE win probability, not Head-to-Head's floored favorite view:
  // six panels each asserting >= 50% would tell the user they are favored in every
  // league while two are lost (design D7).
  const winProb = computeProjectedFinal({
    myProj: matchup.proj,
    oppProj: matchup.opp_proj,
    myRemaining: matchup.remaining.mine,
    oppRemaining: matchup.remaining.theirs,
    clamp: false,
  }).confidencePct;

  return (
    <section
      className="gd-panel"
      data-testid={`gd-panel-${matchup.team_id}`}
      data-live={isLive ? "true" : undefined}
      data-settled={isSettled ? "true" : undefined}
      data-spotlight={isSpotlight ? "true" : undefined}
      // Absent (not "auto") when the user has no preference, so the container query in
      // gameday.css is the only thing deciding — an attribute selector can't match a
      // missing attribute, which is exactly the fall-through we want (design D3).
      data-roster={rosterOverride}
      data-cols={span?.cols ?? 1}
      data-rows={span?.rows ?? 1}
      style={span ? { gridColumn: `span ${span.cols}`, gridRow: `span ${span.rows}` } : undefined}
      {...leadFlip}
    >
      <header
        className="gd-meta"
        draggable={Boolean(onHeaderDragStart)}
        onDragStart={onHeaderDragStart}
        onDragOver={onHeaderDragOver}
        onDrop={onHeaderDrop}
        // Double-click, not click: a single click on the header is the start of a
        // reorder drag, and binding both to one gesture makes each unreliable.
        onDoubleClick={onSpotlight}
      >
        <span className={`pill ${matchup.platform}`}>{matchup.platform.toUpperCase()}</span>
        <span className="gd-team-name">{matchup.team_name}</span>
        <span className="gd-league-name">{matchup.league_name}</span>
        {live > 0 && (
          <span className="pill live gd-live-pill">
            <span className="gd-live-dot" aria-hidden="true" />
            {live}
          </span>
        )}
        {isSettled && <span className="pill bench gd-final-pill">FINAL</span>}
        {onSpotlight && (
          <button
            type="button"
            className="gd-spotlight-btn"
            aria-label={`Spotlight ${matchup.team_name}`}
            onClick={onSpotlight}
          >
            ⤢
          </button>
        )}
      </header>

      <div className="gd-scores">
        {/* Only the LABELS carry color; the values stay white and the trailing side
            drops to --text-secondary, so "who is winning" reads as a brightness
            difference from across the room before any number is read (design D1). */}
        <div className="gd-score-side" data-side="mine" data-trailing={!tied && margin < 0}>
          <div className="gd-score-label">
            <TeamLogo
              team={{ name: matchup.team_name, logo_url: matchup.team_logo_url }}
              size={14}
            />
            {matchup.team_name.toUpperCase()}
          </div>
          <div className="gd-score-value">{matchup.score.toFixed(1)}</div>
          <div className="gd-score-sub">
            {matchup.record.w}–{matchup.record.l} · {matchup.rank.current} of {matchup.rank.total}
          </div>
        </div>

        <div className="gd-margin-chip" data-sign={tied ? "tied" : margin > 0 ? "pos" : "neg"}>
          {tied ? "TIED" : formatSigned(margin)}
        </div>

        <div className="gd-score-side" data-side="theirs" data-trailing={!tied && margin > 0}>
          <div className="gd-score-label">
            <TeamLogo
              team={{ name: matchup.opp_team_name, logo_url: matchup.opp_logo_url }}
              size={14}
            />
            {matchup.opp_team_name.toUpperCase()}
          </div>
          <div className="gd-score-value">{matchup.opp_score.toFixed(1)}</div>
          <div className="gd-score-sub">&nbsp;</div>
        </div>
      </div>

      <div className="gd-stats">
        <div className="gd-stat">
          <div className="gd-stat-label">Projected</div>
          <div className="gd-stat-value">
            {Math.round(matchup.proj)}
            <span className="gd-stat-unit">vs {Math.round(matchup.opp_proj)}</span>
          </div>
        </div>
        <div className="gd-stat">
          <div className="gd-stat-label">Win prob</div>
          <div className="gd-stat-value">
            {winProb}
            <span className="gd-stat-unit">%</span>
          </div>
        </div>
        <div className="gd-stat">
          <div className="gd-stat-label">Yet to play</div>
          <div className="gd-stat-value">
            {matchup.remaining.mine}
            <span className="gd-stat-unit">vs {matchup.remaining.theirs}</span>
          </div>
        </div>
      </div>

      {onToggleRoster && (
        <button
          type="button"
          className="gd-disclosure"
          onClick={handleToggleRoster}
          aria-expanded={rosterOverride === "open"}
        >
          {rosterOverride === "open" ? "⌃ HIDE MATCHUP" : "⌄ FULL MATCHUP"}
        </button>
      )}

      {/* Rendered unconditionally, at every width and arrangement (design D3). CSS
          cannot set React state, so "open by default at >= 540px" cannot be a useState
          initializer — the container query hides it below that instead, and the
          disclosure sets data-roster to override the query in either direction. Cost:
          6 panels x 9 rows of DOM. */}
      <MirroredRoster rosterRef={rosterRef} slots={matchup.slots} iAmHome={matchup.i_am_home} />

      {onResizePointerDown && (
        <span
          className="gd-resize-handle"
          role="separator"
          aria-label={`Resize ${matchup.team_name} panel`}
          // stopPropagation on pointerdown keeps the header's reorder drag from also
          // starting; the two gestures live on disjoint targets by design.
          onPointerDown={(event) => {
            event.stopPropagation();
            onResizePointerDown(event);
          }}
        />
      )}
    </section>
  );
}
