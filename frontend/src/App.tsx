import { Outlet, useLocation } from "react-router-dom";

import { useLiveEvents } from "./api/events";
import { HighlightCelebration } from "./components/shell/HighlightCelebration";
import { Sidebar } from "./components/shell/Sidebar";
import { TabBar } from "./components/shell/TabBar";
import { TeamContextBar } from "./components/shell/TeamContextBar";
import { Topbar } from "./components/shell/Topbar";
import { useActiveTeamSync } from "./hooks/useActiveTeam";
import { parseTeamRoute } from "./hooks/teamRoute";
import { useCurrentWeekDefault } from "./hooks/useCurrentWeekDefault";
import { useUiStore } from "./stores/ui";

// The shell. Layout comes from CSS tokens alone: the developer tweaks panel and the
// per-route aurora tint are gone (design/apple-audit.md, M4 and C2). Persisted tweak
// values are still tolerated in storage and simply no longer applied.
export default function App() {
  const location = useLocation();
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  useCurrentWeekDefault();
  useLiveEvents();
  useActiveTeamSync();

  const teamRoute = parseTeamRoute(location.pathname);

  return (
    <div className="app" data-sidebar={sidebarCollapsed ? "collapsed" : undefined}>
      <Sidebar />
      <div className="main">
        <Topbar />
        <main className="content">
          <div className="content-inner" data-testid="content-inner">
            {/* Rendered by the shell rather than by each team screen, so the bar keeps
                its identity across a team/section switch. */}
            {teamRoute && <TeamContextBar teamId={teamRoute.teamId} section={teamRoute.section} />}
            <Outlet />
          </div>
        </main>
      </div>
      <TabBar />
      <HighlightCelebration />
    </div>
  );
}
