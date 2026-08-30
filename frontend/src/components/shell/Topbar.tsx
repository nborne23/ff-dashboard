// Ported from design/shell.jsx's Topbar. Week state now comes from the
// zustand ui store instead of local App state. The refresh button (Phase 4.7)
// POSTs /api/admin/refresh and invalidates the `teams` query on success. The
// freshness caption next to it (task 8.8) reads `meta.as_of` off the same
// `teams` query Dashboard already populates, so mounting it here doesn't cost
// an extra fetch when Dashboard is also on screen. DayRings (task 10.6) and the
// live-team count (P8 leftover) are both now real, backed by `team.is_live`
// (backend/gridiron/services/fantasy_service.py) and GET /api/teams/day-rings.

import { useRefresh } from "../../api/admin";
import { useDayRings } from "../../api/dayRings";
import { useTeams } from "../../api/teams";
import { useFreshness } from "../../hooks/useFreshness";
import { useUiStore } from "../../stores/ui";
import { DayRings, IconArrowL, IconArrowR, IconMenu, IconRefresh } from "../primitives";

export function Topbar() {
  const week = useUiStore((s) => s.week);
  const setWeek = useUiStore((s) => s.setWeek);
  const mobileNavOpen = useUiStore((s) => s.mobileNavOpen);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);
  const refresh = useRefresh();
  const teamsQuery = useTeams(week);
  const dayRingsQuery = useDayRings(week);
  const freshness = useFreshness(teamsQuery.data?.meta?.as_of);

  const liveCount = teamsQuery.data?.data?.teams?.filter((t) => t.is_live).length ?? 0;
  const dayRingsData = dayRingsQuery.data?.data;

  return (
    <header className="topbar">
      {/* Phone-only: the sidebar is an off-canvas drawer below 768px, and this is the
          only way to open it. Hidden by CSS at desktop widths, where the sidebar is
          always on screen. */}
      <button
        type="button"
        className="nav-toggle"
        aria-label="Open navigation"
        aria-expanded={mobileNavOpen}
        onClick={() => setMobileNavOpen(!mobileNavOpen)}
      >
        <IconMenu size={18} />
      </button>
      <div className="week-nav">
        <button
          type="button"
          className="icon-btn"
          onClick={() => setWeek(week - 1)}
          aria-label="Previous week"
        >
          <IconArrowL size={16} />
        </button>
        <span className="week-label">Week {week}</span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => setWeek(week + 1)}
          aria-label="Next week"
        >
          <IconArrowR size={16} />
        </button>
      </div>
      <DayRings days={dayRingsData?.days ?? []} today={dayRingsData?.today_index ?? -1} />
      <div className="right-cluster">
        <span className="live-badge">
          <span className="dot" />
          {liveCount} LIVE
        </span>
        <span className={"freshness" + (freshness.stale ? " stale" : "")}>{freshness.label}</span>
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
