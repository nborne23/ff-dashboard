// Loading state for the Game Day stage, following the `H2HSkeleton` approach in
// screens/HeadToHead/index.tsx: match the loaded geometry closely enough that the
// stage does not reflow when data arrives.
//
// The panel count is the arrangement's natural fill rather than a guess — the real
// count is unknown until the envelope lands, and rendering too few would shift the
// stage upward on arrival.

import { Skeleton } from "../../components/primitives";
import type { GameDayMode } from "../../stores/ui";

const SKELETON_PANELS: Record<GameDayMode, number> = {
  g2: 4,
  g3: 6,
  c4: 8,
  spot: 4,
};

export function GameDaySkeleton({ mode }: { mode: GameDayMode }) {
  return (
    <div className="gd-stage" data-layout={mode} data-testid="gameday-loading" aria-hidden="true">
      {Array.from({ length: SKELETON_PANELS[mode] }).map((_, i) => (
        <div key={i} className="gd-panel gd-panel-skeleton">
          <div className="gd-meta">
            <Skeleton width={52} height={16} radius={999} />
            <Skeleton width="40%" height={14} />
          </div>
          <div className="gd-scores">
            <div className="gd-score-side">
              <Skeleton width="80%" height={12} />
              <div style={{ height: 8 }} />
              <Skeleton width="60%" height={40} />
            </div>
            <Skeleton width={64} height={26} radius={999} />
            <div className="gd-score-side">
              <Skeleton width="80%" height={12} />
              <div style={{ height: 8 }} />
              <Skeleton width="60%" height={40} />
            </div>
          </div>
          <div className="gd-stats">
            {Array.from({ length: 3 }).map((_, j) => (
              <div key={j} className="gd-stat">
                <Skeleton width="60%" height={11} />
                <div style={{ height: 6 }} />
                <Skeleton width="50%" height={18} />
              </div>
            ))}
          </div>
          <div className="gd-roster">
            {Array.from({ length: 9 }).map((_, j) => (
              <Skeleton key={j} width="100%" height={22} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
