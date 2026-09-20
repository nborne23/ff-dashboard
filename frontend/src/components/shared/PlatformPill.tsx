// The ESPN/Yahoo badge, shared by every screen that names a team's platform.
//
// It lived in the Dashboard's TeamCard until that screen was removed; it is a leaf with
// no data dependencies, so it belongs here rather than inside any one screen.

import type { Platform } from "../../types/api";

export function PlatformPill({ platform }: { platform: Platform | null }) {
  if (platform === "yahoo") return <span className="pill yahoo">YAHOO</span>;
  if (platform === "espn") return <span className="pill espn">ESPN</span>;
  return null;
}
