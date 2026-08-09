// Shared full-page empty state (task 10.3) — shown by every data screen
// (Dashboard/MyTeam/HeadToHead/Season) when neither platform is connected. Generalizes
// Dashboard's original "Connect a league" block (same DOM/classNames) so the other three
// screens don't each hand-roll their own copy.

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { IconShield } from "../primitives";

export interface EmptyStateProps {
  title?: string;
  subtitle?: string;
  icon?: ReactNode;
  testId?: string;
}

export function EmptyState({
  title = "Connect a league",
  subtitle = "Link your Yahoo or ESPN fantasy account in Settings to see your teams here.",
  icon,
  testId = "empty-state",
}: EmptyStateProps) {
  return (
    <div
      data-testid={testId}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "60vh",
        textAlign: "center",
        gap: 16,
      }}
    >
      {icon ?? <IconShield size={40} />}
      <h1 className="large-title" style={{ marginBottom: 0 }}>
        {title}
      </h1>
      <p className="large-subtitle" style={{ marginBottom: 0, maxWidth: 360 }}>
        {subtitle}
      </p>
      <Link to="/settings" className="btn primary">
        Go to Settings
      </Link>
    </div>
  );
}
