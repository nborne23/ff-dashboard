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

import { PlayerHealth } from "../../components/shared/PlayerHealth";
import { ProjectionCompare } from "../../components/shared/ProjectionCompare";
import type { WaiverCandidate } from "../../types/api";

/** An absent value renders as an em dash, never as a number.
 *
 * This is load-bearing, not cosmetic. `null` means "no projection published" while
 * `0.0` means "projected to score nothing" — both occur in real data (roughly 430
 * players per league have no projection, ~50 genuinely project zero). Rendering them
 * identically would present a player the system knows nothing about as one it has
 * actively judged worthless. */
function formatPoints(value: number | null | undefined): string {
  // `undefined` is accepted alongside `null` deliberately. The type says these fields
  // are always present, but a browser holding a cached bundle newer than the backend it
  // is talking to gets `undefined` — and `undefined.toFixed()` threw, taking the entire
  // Waivers screen down to the error boundary rather than dropping one number.
  return value === null || value === undefined ? "—" : value.toFixed(1);
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
function DeltaCell({ delta }: { delta: number | null | undefined }) {
  if (delta === null || delta === undefined) {
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
              {/* The most expensive place to miss a designation: an IR stash looks like
                  a bargain on projection alone. */}
              <PlayerHealth
                playerId={player.id}
                playerName={player.name}
                status={player.injury_status}
              />
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
      <td className="num muted roster-col-proj">
        <div className="waiver-stack">
          <span>{formatPoints(candidate.week_proj_points)}</span>
          <span className="waiver-stack-season">{formatPoints(candidate.season_proj_points)}</span>
        </div>
      </td>
      <td className="num roster-col-proj-ext">
        {candidate.season_proj_points === null ? (
          <span className="proj-ext muted">—</span>
        ) : (
          <ProjectionCompare
            own={candidate.season_proj_points}
            ext={candidate.ext_season_proj_points}
          />
        )}
      </td>
      <td className="num roster-col-actual">
        {/* Both horizons, because they disagree often enough to matter: a player on
            bye is a season-long keep and a week-one hole, and a short-term streamer is
            the reverse. Neither number alone answers "should I claim him". */}
        <div className="waiver-stack">
          <DeltaCell delta={candidate.delta_vs_worst_starter_week} />
          <span className="waiver-stack-season">
            <DeltaCell delta={candidate.delta_vs_worst_starter} />
          </span>
        </div>
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
            <th
              className="roster-col-proj"
              title="Projected points — this week on top, full season beneath"
            >
              Proj
              <span className="th-sub">wk / szn</span>
            </th>
            <th className="roster-col-proj-ext" title="Rotowire's independent season projection">
              RW
            </th>
            <th
              className="roster-col-actual"
              title="Points gained over your weakest eligible starter — this week on top, full season beneath"
            >
              Upgrade
              <span className="th-sub">wk / szn</span>
            </th>
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
