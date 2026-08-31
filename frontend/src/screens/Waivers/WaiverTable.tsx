// Reuses `.roster`'s table classes and the `roster-col-*` width vocabulary rather
// than defining a parallel set. Those already carry the mobile rules — table-layout:
// fixed with percentage widths, and the column-hiding that keeps the table inside a
// 375px viewport — so a second set would have to re-solve all of it and would drift.
//
// Column mapping onto the roster widths:
//   roster-col-slot    -> rank        (narrow, leading)
//   roster-col-player  -> player cell (headshot + name + position pill)
//   roster-col-opp     -> NFL team    (hidden on mobile, as on the roster)
//   roster-col-status  -> % rostered ("Own" — "Rostered" truncates to "ROST…" in
//                        the 55px mobile column)
//   roster-col-proj    -> season projection
//   roster-col-actual  -> delta chip  (the column that carries the decision)

import { useState } from "react";

import type { WaiverCandidate } from "../../types/api";

/** An absent value renders as an em dash, never as a number.
 *
 * This is load-bearing, not cosmetic. `null` means "no projection published" while
 * `0.0` means "projected to score nothing" — both occur in real data (roughly 430
 * players per league have no projection, ~50 genuinely project zero). Rendering them
 * identically would present a player the system knows nothing about as one it has
 * actively judged worthless. */
function formatPoints(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

function initialsFor(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
}

function Headshot({ name, url }: { name: string; url: string }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) {
    return <div className="headshot">{initialsFor(name)}</div>;
  }
  return (
    <div className="headshot">
      <img
        src={url}
        alt=""
        onError={() => setFailed(true)}
        style={{ width: "100%", height: "100%", borderRadius: "50%", objectFit: "cover" }}
      />
    </div>
  );
}

/** The delta against the user's weakest eligible starter — the column the screen
 *  exists for. Reuses `.delta`'s pos/neg/zero styling from the roster. */
function DeltaCell({ delta }: { delta: number | null }) {
  if (delta === null) {
    return <span className="muted">—</span>;
  }
  const tone = delta > 0.05 ? "pos" : delta < -0.05 ? "neg" : "zero";
  return (
    <span className={"delta " + tone}>
      {delta > 0 ? "+" : ""}
      {delta.toFixed(1)}
    </span>
  );
}

function WaiverRow({ candidate, rank }: { candidate: WaiverCandidate; rank: number }) {
  const { player } = candidate;
  return (
    <tr>
      <td
        className="roster-col-slot"
        style={{
          fontWeight: 700,
          fontSize: 13,
          color: "var(--text-secondary)",
          letterSpacing: "0.05em",
        }}
      >
        {rank}
      </td>
      <td className="roster-col-player">
        <div className="player-cell">
          <Headshot name={player.name} url={player.headshot_url} />
          <div className="player-info">
            <div className="player-info-row">
              <span className="player-name">{player.name}</span>
              <span className="pill pos">{player.position}</span>
            </div>
            <div className="player-meta">{player.nfl_team}</div>
          </div>
        </div>
      </td>
      <td className="muted roster-col-opp">{player.nfl_team}</td>
      <td className="roster-col-status">
        <span className="muted" style={{ fontSize: 12 }}>
          {candidate.percent_owned.toFixed(0)}%
        </span>
      </td>
      <td className="num muted roster-col-proj">{formatPoints(candidate.season_proj_points)}</td>
      <td className="num roster-col-actual">
        <DeltaCell delta={candidate.delta_vs_worst_starter} />
      </td>
    </tr>
  );
}

export interface WaiverTableProps {
  candidates: WaiverCandidate[];
}

export function WaiverTable({ candidates }: WaiverTableProps) {
  if (candidates.length === 0) {
    return (
      <div className="card" style={{ padding: 24, textAlign: "center" }}>
        <div className="muted">No available players match this filter.</div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="roster">
        <thead>
          <tr>
            <th className="roster-col-slot">#</th>
            <th className="roster-col-player">Player</th>
            <th className="roster-col-opp">Team</th>
            <th className="roster-col-status">Own</th>
            <th className="roster-col-proj">Proj</th>
            <th className="roster-col-actual">Upgrade</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c, i) => (
            <WaiverRow key={c.player.id} candidate={c} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
