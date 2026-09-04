// A second, independent projection shown next to the platform's own.
//
// The point of this component is the DISAGREEMENT, not the number. ESPN and Yahoo
// publish the weakest projections in the market; Rotowire's (relayed free through
// Sleeper's public feed) are an independent read on the same player. Where the two
// agree there is nothing to think about — where they diverge by a couple of points is
// exactly where a start/sit decision lives.
//
// So: the secondary number renders quietly, and only the GAP is given colour.

export interface ProjectionCompareProps {
  /** The league platform's own projection — always present. */
  own: number;
  /** The independent projection, or null when unmatched / job not yet run / custom
   *  scoring. `undefined` is tolerated for the same reason `formatPoints` tolerates it:
   *  a bundle newer than the backend it talks to must degrade to a dash, not throw. */
  ext: number | null | undefined;
}

/** Below this the two sources are saying the same thing and the delta is noise. */
export const DIVERGENCE_THRESHOLD = 1.5;

export function ProjectionCompare({ own, ext }: ProjectionCompareProps) {
  if (ext === null || ext === undefined) {
    return <span className="proj-ext muted">—</span>;
  }

  const delta = ext - own;
  const diverges = Math.abs(delta) >= DIVERGENCE_THRESHOLD;
  const tone = delta > 0 ? "pos" : "neg";

  return (
    <span
      className={"proj-ext" + (diverges ? ` proj-ext-diverges ${tone}` : "")}
      title={
        diverges
          ? `Rotowire ${ext.toFixed(1)} vs platform ${own.toFixed(1)} — ${
              delta > 0 ? "higher" : "lower"
            } by ${Math.abs(delta).toFixed(1)}`
          : `Rotowire ${ext.toFixed(1)} — agrees with the platform`
      }
    >
      {ext.toFixed(1)}
    </span>
  );
}
