// The top bar: a translucent material the content scrolls under (§12), holding the
// week stepper and the data's status. It is the ONE place freshness is shown; the
// sidebar footer used to repeat it.
//
// The live count appears only when something is live. A permanent "0 LIVE" taught the
// eye to ignore the one badge whose job is to be noticed.

import { useRefresh } from "../../api/admin";
import { useTeams } from "../../api/teams";
import { useFreshness } from "../../hooks/useFreshness";
import { useLiveConnectionStore } from "../../stores/live";
import { useUiStore } from "../../stores/ui";
import { IconArrowL, IconArrowR, IconRefresh } from "../primitives";

export function Topbar() {
  const week = useUiStore((s) => s.week);
  const setWeek = useUiStore((s) => s.setWeek);
  const refresh = useRefresh();
  const teamsQuery = useTeams(week);
  const freshness = useFreshness(teamsQuery.data?.meta?.as_of);
  const connectionLostLong = useLiveConnectionStore((s) => s.connectionLostLong);

  const liveCount = teamsQuery.data?.data?.teams?.filter((t) => t.is_live).length ?? 0;

  return (
    <header className="topbar">
      <div className="week-nav" role="group" aria-label="Week">
        <button
          type="button"
          className="icon-btn"
          onClick={() => setWeek(week - 1)}
          aria-label="Previous week"
        >
          <IconArrowL size={16} />
        </button>
        <span className="week-label" aria-live="polite">
          Week {week}
        </span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => setWeek(week + 1)}
          aria-label="Next week"
        >
          <IconArrowR size={16} />
        </button>
      </div>

      <div className="right-cluster">
        {liveCount > 0 && (
          <span className="live-badge" data-testid="live-badge">
            <span className="dot" aria-hidden="true" />
            {liveCount} live
          </span>
        )}
        {/* Only the rare connection-lost message is announced; the freshness label ticks
            every second and would talk over everything else. */}
        {connectionLostLong ? (
          <span className="freshness lost" role="status">
            Connection lost — retrying
          </span>
        ) : (
          <span className={"freshness" + (freshness.stale ? " stale" : "")}>{freshness.label}</span>
        )}
        <button
          type="button"
          className="icon-btn"
          aria-label="Refresh"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          <span className={refresh.isPending ? "icon-spin" : undefined} style={{ display: "flex" }}>
            <IconRefresh size={16} />
          </span>
        </button>
      </div>
    </header>
  );
}
