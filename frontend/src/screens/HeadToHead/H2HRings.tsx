// Ported from design/screen-h2h.jsx's H2HRings. Unlike the prototype (which
// hardcodes "me = home"), scores/projections are passed in pre-oriented (see
// ./orientation.ts) so this component never has to know which side of the
// Matchup is "mine".

import { ActivityRing } from "../../components/primitives";

export interface H2HRingsProps {
  myScore: number;
  myProj: number;
  oppScore: number;
  oppProj: number;
  gamesLeft: number;
}

export function H2HRings({ myScore, myProj, oppScore, oppProj, gamesLeft }: H2HRingsProps) {
  const diff = myScore - oppScore;
  const leading = diff >= 0;
  return (
    <div style={{ position: "relative", display: "inline-grid", placeItems: "center" }}>
      <ActivityRing
        size={200}
        stroke={16}
        gap={4}
        tracks={[
          { value: myProj > 0 ? myScore / myProj : 0, color: "var(--move)" },
          { value: oppProj > 0 ? oppScore / oppProj : 0, color: "var(--stand)" },
        ]}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "grid",
          placeItems: "center",
          textAlign: "center",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            Lead
          </div>
          <div
            className="tnum"
            style={{
              fontSize: 38,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: leading ? "var(--move)" : "var(--stand)",
            }}
          >
            {diff >= 0 ? "+" : ""}
            {diff.toFixed(1)}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{gamesLeft} games left</div>
        </div>
      </div>
    </div>
  );
}
