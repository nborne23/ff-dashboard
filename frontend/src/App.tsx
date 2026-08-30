import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { useLiveEvents } from "./api/events";
import { Aurora } from "./components/shell/Aurora";
import { Sidebar } from "./components/shell/Sidebar";
import { Topbar } from "./components/shell/Topbar";
import { TweaksPanel } from "./components/shell/TweaksPanel";
import { useWeekParam } from "./hooks/useWeekParam";
import { COLLAPSED_SIDEBAR_W, useUiStore } from "./stores/ui";

// Per-route aurora tint, matching design/app.jsx's SCREEN_AURORAS table.
// Dashboard ("/") and MyTeam ("/team/:teamId") share the pink aurora; H2H,
// Season, and Settings each get their own.
function auroraColorForPath(pathname: string, intensity: number): string {
  // Game Day gets the live orange, the one screen whose whole point is games in
  // progress; every other screen keeps the tint it already had.
  if (pathname === "/gameday") return `rgba(255, 159, 10, ${intensity})`;
  if (pathname.endsWith("/h2h")) return `rgba(191, 90, 242, ${intensity})`;
  if (pathname.endsWith("/season")) return `rgba(100, 210, 255, ${intensity})`;
  if (pathname === "/settings") return `rgba(142, 142, 147, ${intensity})`;
  return `rgba(255, 45, 85, ${intensity})`;
}

export default function App() {
  const location = useLocation();
  const tweaks = useUiStore((s) => s.tweaks);
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const mobileNavOpen = useUiStore((s) => s.mobileNavOpen);
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);
  useWeekParam();
  useLiveEvents();

  useEffect(() => {
    const root = document.documentElement;
    // One source of truth for the grid column: collapsing overrides the tweak's width
    // rather than the two fighting over `--sidebar-w`.
    root.style.setProperty(
      "--sidebar-w",
      `${sidebarCollapsed ? COLLAPSED_SIDEBAR_W : tweaks.sidebarWidth}px`,
    );
    root.style.setProperty("--row-h", `${tweaks.rowHeight}px`);
    root.style.setProperty("--spark-thick", `${tweaks.sparkThickness}px`);
  }, [tweaks.sidebarWidth, tweaks.rowHeight, tweaks.sparkThickness, sidebarCollapsed]);

  // Close the drawer whenever the route changes. Without this, tapping a nav item
  // navigates but leaves the drawer covering the screen you just asked for.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, setMobileNavOpen]);

  // Escape closes it too, for the keyboard case (and for a phone with a keyboard).
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen, setMobileNavOpen]);

  const auroraColor = auroraColorForPath(location.pathname, tweaks.auroraIntensity);

  return (
    <div
      className="app"
      data-sidebar={sidebarCollapsed ? "collapsed" : undefined}
      data-nav={mobileNavOpen ? "open" : undefined}
    >
      <Sidebar />
      {/* Backdrop is rendered only while open so it can never intercept taps on
          desktop, where the drawer does not exist. */}
      {mobileNavOpen && (
        <div
          className="nav-backdrop"
          data-testid="nav-backdrop"
          role="presentation"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
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
