import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { useLiveEvents } from "./api/events";
import { Aurora } from "./components/shell/Aurora";
import { Sidebar } from "./components/shell/Sidebar";
import { Topbar } from "./components/shell/Topbar";
import { TweaksPanel } from "./components/shell/TweaksPanel";
import { useWeekParam } from "./hooks/useWeekParam";
import { useUiStore } from "./stores/ui";

// Per-route aurora tint, matching design/app.jsx's SCREEN_AURORAS table.
// Dashboard ("/") and MyTeam ("/team/:teamId") share the pink aurora; H2H,
// Season, and Settings each get their own.
function auroraColorForPath(pathname: string, intensity: number): string {
  if (pathname.endsWith("/h2h")) return `rgba(191, 90, 242, ${intensity})`;
  if (pathname.endsWith("/season")) return `rgba(100, 210, 255, ${intensity})`;
  if (pathname === "/settings") return `rgba(142, 142, 147, ${intensity})`;
  return `rgba(255, 45, 85, ${intensity})`;
}

export default function App() {
  const location = useLocation();
  const tweaks = useUiStore((s) => s.tweaks);
  useWeekParam();
  useLiveEvents();

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--sidebar-w", `${tweaks.sidebarWidth}px`);
    root.style.setProperty("--row-h", `${tweaks.rowHeight}px`);
    root.style.setProperty("--spark-thick", `${tweaks.sparkThickness}px`);
  }, [tweaks.sidebarWidth, tweaks.rowHeight, tweaks.sparkThickness]);

  const auroraColor = auroraColorForPath(location.pathname, tweaks.auroraIntensity);

  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <Aurora color={auroraColor} />
        <Topbar />
        <div className="content">
          <div className="content-inner" data-testid="content-inner">
            <Outlet />
          </div>
        </div>
      </div>
      <TweaksPanel />
    </div>
  );
}
