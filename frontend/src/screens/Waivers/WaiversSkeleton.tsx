// Matches the loaded geometry — title, subtitle, filter row, then table rows —
// following the SeasonSkeleton approach in screens/Season/index.tsx.

import { Skeleton } from "../../components/primitives";

export function WaiversSkeleton() {
  return (
    <div data-testid="waivers-loading" aria-hidden="true">
      <Skeleton width="20%" height={34} radius={6} />
      <div style={{ height: 8 }} />
      <Skeleton width="35%" height={15} />
      <div className="spacer-md" />

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {Array.from({ length: 7 }).map((_, i) => (
          <Skeleton key={i} width={54} height={30} radius={15} />
        ))}
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "10px 14px",
            }}
          >
            <Skeleton width={20} height={14} />
            <Skeleton width={32} height={32} radius={16} />
            <Skeleton width="40%" height={14} />
            <div style={{ flex: 1 }} />
            <Skeleton width={48} height={14} />
          </div>
        ))}
      </div>
    </div>
  );
}
