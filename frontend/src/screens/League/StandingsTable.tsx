// Reuses `.roster`'s table classes and the `roster-col-*` width vocabulary rather than
// a parallel set — those already carry the mobile rules (table-layout: fixed with
// percentage widths, plus the column hiding that keeps a table inside 375px).
//
// Column mapping, chosen so the least decision-relevant column is the one that
// disappears on a phone:
//   roster-col-slot    -> rank
//   roster-col-player  -> logo + team name + manager
//   roster-col-opp     -> points against  (HIDDEN on mobile — the least useful number)
//   roster-col-status  -> record
//   roster-col-proj    -> points for
//   roster-col-actual  -> points against on desktop is redundant; used for PF delta-free
//                         alignment of the record column instead. See below.

import { TeamLogo } from "../../components/shared/TeamLogo";
import type { LeagueStandingsRow } from "../../types/api";

function recordText(record: { w: number; l: number; t: number }): string {
  return record.t > 0 ? `${record.w}-${record.l}-${record.t}` : `${record.w}-${record.l}`;
}

function StandingsRow({ row }: { row: LeagueStandingsRow }) {
  const { team } = row;
  return (
    <tr className={team.is_user_team ? "live-row" : ""} data-own={team.is_user_team || undefined}>
      <td
        className="roster-col-slot"
        style={{
          fontWeight: 700,
          fontSize: 13,
          color: team.is_user_team ? "var(--move)" : "var(--text-secondary)",
        }}
      >
        {row.position}
      </td>
      <td className="roster-col-player">
        <div className="player-cell">
          <TeamLogo team={team} size={32} />
          <div className="player-info">
            <div className="player-info-row">
              <span className="player-name" style={team.is_user_team ? { fontWeight: 700 } : undefined}>
                {team.name}
              </span>
            </div>
            <div className="player-meta">{team.manager_name}</div>
          </div>
        </div>
      </td>
      <td className="roster-col-status">
        <span style={{ fontSize: 13, fontWeight: 600 }}>{recordText(team.record)}</span>
      </td>
      <td className="num roster-col-proj">{team.points_for.toFixed(1)}</td>
      <td className="num muted roster-col-opp">{team.points_against.toFixed(1)}</td>
    </tr>
  );
}

export interface StandingsTableProps {
  rows: LeagueStandingsRow[];
}

export function StandingsTable({ rows }: StandingsTableProps) {
  if (rows.length === 0) {
    return (
      <div className="card" style={{ padding: 24, textAlign: "center" }}>
        <div className="muted">No teams in this league yet.</div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="roster">
        <thead>
          <tr>
            <th className="roster-col-slot">#</th>
            <th className="roster-col-player">Team</th>
            <th className="roster-col-status">Rec</th>
            <th className="roster-col-proj">PF</th>
            <th className="roster-col-opp">PA</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <StandingsRow key={row.team.id} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
