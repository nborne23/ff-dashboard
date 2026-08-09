// Ambient aurora glow behind the topbar. Ported 1:1 from design/shell.jsx —
// the per-route color selection lives in App.tsx (this component just paints
// whatever color it's given via the --aurora-color custom property).

import type { CSSProperties } from "react";

export interface AuroraProps {
  color?: string;
}

export function Aurora({ color = "rgba(255, 45, 85, 0.18)" }: AuroraProps) {
  const style = { "--aurora-color": color } as CSSProperties;
  return <div className="aurora" style={style} />;
}
