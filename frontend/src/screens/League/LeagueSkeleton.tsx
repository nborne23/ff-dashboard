// Matches the loaded geometry — title, subtitle, then table rows with a logo-sized
// square where each crest goes — following the SeasonSkeleton approach.

import { Skeleton } from "../../components/primitives";

export function LeagueSkeleton() {
  return (
    <div data-testid="league-loading" aria-hidden="true">
      <Skeleton width="20%" height={34} radius={6} />
      <div style={{ height: 8 }} />
      <Skeleton width="35%" height={15} />
      <div className="spacer-md" />

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px" }}
          >
            <Skeleton width={16} height={14} />
            <Skeleton width={32} height={32} radius={6} />
            <Skeleton width="35%" height={14} />
            <div style={{ flex: 1 }} />
            <Skeleton width={40} height={14} />
            <Skeleton width={48} height={14} />
          </div>
        ))}
      </div>
    </div>
  );
}
