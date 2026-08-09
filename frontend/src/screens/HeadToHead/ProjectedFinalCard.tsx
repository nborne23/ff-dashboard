// Ported from design/screen-h2h.jsx's "Projected Final" card. Range and
// confidence come from ./projectedFinal.ts's client-side normal
// approximation (task 5.8) rather than the prototype's static numbers.

import { IconCheck } from "../../components/primitives";
import { computeProjectedFinal } from "./projectedFinal";

export interface ProjectedFinalCardProps {
  myProj: number;
  oppProj: number;
  myRemaining: number;
  oppRemaining: number;
}

export function ProjectedFinalCard({
  myProj,
  oppProj,
  myRemaining,
  oppRemaining,
}: ProjectedFinalCardProps) {
  const result = computeProjectedFinal({ myProj, oppProj, myRemaining, oppRemaining });
  const diff = myProj - oppProj;
  const range = result.myCeiling - result.myFloor;
  const markerPct =
    range > 0 ? Math.min(100, Math.max(0, ((myProj - result.myFloor) / range) * 100)) : 50;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--exercise)" }}>
          <IconCheck size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--exercise)" }}>
          Projected Final
        </span>
        <span className="ts">Confidence {result.confidencePct}%</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 8 }}>
        <span className="metric" style={{ fontSize: 36 }}>
          {myProj.toFixed(1)}
        </span>
        <span className="vs" style={{ color: "var(--text-secondary)", fontSize: 18 }}>
          –
        </span>
        <span className="metric" style={{ fontSize: 36, color: "var(--text-secondary)" }}>
          {oppProj.toFixed(1)}
        </span>
      </div>
      <div style={{ marginTop: 16 }}>
        <div
          style={{
            fontSize: 11,
            color: "var(--text-secondary)",
            marginBottom: 6,
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <span>
            Range: {result.myFloor.toFixed(0)} – {result.myCeiling.toFixed(0)}
          </span>
          <span className="num">
            {diff >= 0 ? "+" : ""}
            {diff.toFixed(1)}
          </span>
        </div>
        <div
          style={{
            position: "relative",
            height: 8,
            background: "rgba(255,255,255,0.06)",
            borderRadius: 999,
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 0,
              bottom: 0,
              background:
                "linear-gradient(90deg, rgba(255,45,85,0.15), var(--move) 50%, rgba(255,45,85,0.15))",
              borderRadius: 999,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${markerPct}%`,
              top: -4,
              bottom: -4,
              width: 2,
              background: "var(--text)",
              borderRadius: 1,
            }}
          />
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--text-secondary)",
            marginTop: 4,
          }}
        >
          <span>floor</span>
          <span>likely {myProj.toFixed(1)}</span>
          <span>ceiling</span>
        </div>
      </div>
    </div>
  );
}
