// Shared loading-placeholder primitive (task 10.1). Every screen's loading state was
// hand-rolling its own `{width, height, borderRadius: 4, background: "var(--pill)",
// opacity: 0.5}` block (Dashboard's TeamCardSkeleton, MyTeam's RosterSkeleton,
// Settings/SettingsRow's SkeletonRow) — this generalizes that one shape instead of
// leaving three near-identical copies. Callers size it to match the real content's
// final dimensions so a loading -> loaded swap causes no layout shift.

import type { CSSProperties } from "react";

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  radius?: number | string;
  circle?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({
  width = "100%",
  height = 14,
  radius = 4,
  circle = false,
  className,
  style,
}: SkeletonProps) {
  return (
    <div
      className={["skeleton", className].filter(Boolean).join(" ")}
      data-testid="skeleton"
      aria-hidden="true"
      style={{
        width,
        height,
        borderRadius: circle ? "50%" : radius,
        ...style,
      }}
    />
  );
}
