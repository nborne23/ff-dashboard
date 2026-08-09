// Ported from design/screen-h2h.jsx's h2h-table. Each MatchupSlot carries
// home_player/away_player and home_pts/away_pts (design.md D12) — `iAmHome`
// (see ./orientation.ts) resolves which side is mine per row, so this
// component is correct whether the route's teamId is the home or away team.

import type { MatchupSlot } from "../../types/api";
import { orientSlot } from "./orientation";

function initialsFor(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
}

export interface H2HTableProps {
  slots: MatchupSlot[];
  iAmHome: boolean;
  myTeamName: string;
  oppTeamName: string;
}

export function H2HTable({ slots, iAmHome, myTeamName, oppTeamName }: H2HTableProps) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 24 }}>
      <table className="h2h-table">
        <thead>
          <tr>
            <th className="me">{myTeamName}</th>
            <th className="center">Slot</th>
            <th className="opp">{oppTeamName}</th>
          </tr>
        </thead>
        <tbody>
          {slots.map((row) => {
            const { myPlayer, oppPlayer, myPts, oppPts } = orientSlot(row, iAmHome);
            const diff = myPts - oppPts;
            const tie = Math.abs(diff) < 0.05;
            return (
              <tr key={`${row.slot}-${myPlayer.id}`}>
                <td>
                  <div className="me-cell">
                    <div className="headshot">{initialsFor(myPlayer.name)}</div>
                    <div className="player-info">
                      <div className="player-name">{myPlayer.name}</div>
                      <div className="player-meta">{myPts.toFixed(1)} pts</div>
                    </div>
                  </div>
                </td>
                <td className="center">
                  <div className="pos-label">{row.slot}</div>
                  <span className={"diff-chip " + (tie ? "tie" : diff > 0 ? "pos" : "neg")}>
                    {tie ? "TIE" : (diff > 0 ? "+" : "") + diff.toFixed(1)}
                  </span>
                </td>
                <td>
                  <div className="opp-cell">
                    <div className="headshot">{initialsFor(oppPlayer.name)}</div>
                    <div className="player-info">
                      <div className="player-name">{oppPlayer.name}</div>
                      <div className="player-meta">{oppPts.toFixed(1)} pts</div>
                    </div>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
