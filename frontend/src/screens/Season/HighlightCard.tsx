// Ported 1:1 from design/screen-season.jsx's HighlightCard.

import type { ReactNode } from "react";

export interface HighlightCardProps {
  accent: string;
  icon: ReactNode;
  label: string;
  value: string;
  sub: string;
}

export function HighlightCard({ accent, icon, label, value, sub }: HighlightCardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: accent }}>
          {icon}
        </span>
        <span className="cat-label" style={{ color: accent }}>
          {label}
        </span>
      </div>
      <div className="metric" style={{ fontSize: 30, marginTop: 4 }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}
