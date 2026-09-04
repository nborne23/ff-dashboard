// Ported from design/screen-myteam.jsx's RosterTable/RosterRow — DOM
// structure and classNames match verbatim so global.css's `.roster` rules
// apply unmodified. Unlike the prototype (which hardcodes `initials` text),
// the real Player entity carries a `headshot_url` (design.md D12); we render
// an <img> and fall back to the initials div on load failure (missing local
// cache file) via onError.

import { useState } from "react";

import { PlayerHealth } from "../../components/shared/PlayerHealth";
import { ProjectionCompare } from "../../components/shared/ProjectionCompare";
import type { RosterSlot } from "../../types/api";

function initialsFor(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
}

function PositionPill({ pos }: { pos: string }) {
  return <span className="pill pos">{pos}</span>;
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

function RosterRow({ slot, isBench }: { slot: RosterSlot; isBench?: boolean }) {
  const delta = slot.actual_points - slot.proj_points;
  const isOut = slot.player.injury_status === "O";
  return (
    <tr className={slot.is_live ? "live-row" : isBench ? "bench-row" : ""}>
      <td
        className="roster-col-slot"
        style={{
          fontWeight: 700,
          fontSize: 13,
          color: "var(--text-secondary)",
          letterSpacing: "0.05em",
        }}
      >
        {slot.slot}
      </td>
      <td className="roster-col-player">
        <div className="player-cell">
          <Headshot name={slot.player.name} url={slot.player.headshot_url} />
          <div className="player-info">
            <div className="player-info-row">
              <span className="player-name">{slot.player.name}</span>
              <PositionPill pos={slot.player.position} />
              {/* Beside the position pill, NOT in the Status column: that column is an
                  `is_live ? … : isOut ? … : status_text` chain, so putting Q/D/IR there
                  would replace kickoff time on exactly the rows being decided about. */}
              <PlayerHealth
                playerId={slot.player.id}
                playerName={slot.player.name}
                status={slot.player.injury_status}
              />
            </div>
            <div className="player-meta">{slot.player.nfl_team}</div>
          </div>
        </div>
      </td>
      <td className="muted roster-col-opp">{slot.player.nfl_opponent ?? "—"}</td>
      <td className="roster-col-status">
        {slot.is_live ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              color: "var(--live)",
              fontWeight: 600,
              fontSize: 12,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--live)",
                boxShadow: "0 0 6px var(--live)",
              }}
            />
            {slot.status_text}
          </span>
        ) : isOut ? (
          <span style={{ color: "var(--espn)", fontWeight: 600, fontSize: 12 }}>OUT</span>
        ) : (
          <span className="muted" style={{ fontSize: 12 }}>
            {slot.status_text}
          </span>
        )}
      </td>
      <td className="num muted roster-col-proj">
        {slot.proj_points.toFixed(1)}
        {/* Repeated here for phones, where the RW column is hidden for width. Without
            it the Start/Sit card quotes Rotowire numbers that appear nowhere else on
            the screen, and the two look like a contradiction rather than two sources. */}
        <span className="proj-ext-inline">
          <ProjectionCompare own={slot.proj_points} ext={slot.ext_proj_points} />
        </span>
      </td>
      <td className="num roster-col-proj-ext">
        <ProjectionCompare own={slot.proj_points} ext={slot.ext_proj_points} />
      </td>
      <td className="num roster-col-actual">
        {slot.actual_points ? slot.actual_points.toFixed(1) : "—"}
      </td>
      <td className="roster-col-delta">
        {slot.actual_points > 0 ? (
          <span className={"delta " + (delta > 0.05 ? "pos" : delta < -0.05 ? "neg" : "zero")}>
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
    </tr>
  );
}

export interface RosterTableProps {
  starters: RosterSlot[];
  bench: RosterSlot[];
}

export function RosterTable({ starters, bench }: RosterTableProps) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="roster">
        <thead>
          <tr>
            <th className="roster-col-slot">Slot</th>
            <th className="roster-col-player">Player</th>
            <th className="roster-col-opp">Opp</th>
            <th className="roster-col-status">Status</th>
            <th className="roster-col-proj" title="Your league platform's projection">
              Proj
            </th>
            <th className="roster-col-proj-ext" title="Rotowire's independent projection">
              RW
            </th>
            <th className="roster-col-actual">Actual</th>
            <th className="roster-col-delta">+/–</th>
          </tr>
        </thead>
        <tbody>
          <tr className="section-row">
            <td colSpan={8}>Starters</td>
          </tr>
          {starters.map((s) => (
            <RosterRow key={`${s.slot}-${s.player.id}`} slot={s} />
          ))}
          <tr className="section-row">
            <td colSpan={8}>Bench</td>
          </tr>
          {bench.map((s) => (
            <RosterRow key={`${s.slot}-${s.player.id}`} slot={s} isBench />
          ))}
        </tbody>
      </table>
    </div>
  );
}
