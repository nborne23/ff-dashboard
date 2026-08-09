// Ported from design/screen-dashboard.jsx's TeamCard — DOM structure and
// classNames match verbatim so global.css's `.team-card` rules apply
// unmodified. Team.platform isn't a field on the normalized Team entity
// (per design.md D12); it's derived from the `{platform}:{platform_id}`
// stable id (specs/fantasy-data-model/spec.md, "Stable internal id").

import { useNavigate } from "react-router-dom";

import { Sparkline } from "../../components/primitives";
import { useChangedValuePulse } from "../../hooks/useChangedValuePulse";
import type { Platform, Team } from "../../types/api";
import { platformFromId } from "../../types/api";
import { ordinal } from "./ordinal";

export function PlatformPill({ platform }: { platform: Platform | null }) {
  if (platform === "yahoo") return <span className="pill yahoo">YAHOO</span>;
  if (platform === "espn") return <span className="pill espn">ESPN</span>;
  return null;
}

export interface TeamCardProps {
  team: Team;
}

export function TeamCard({ team }: TeamCardProps) {
  const navigate = useNavigate();
  const scorePulse = useChangedValuePulse(team.current_score);
  const winning = team.current_score >= team.current_opp_score;
  const platform = platformFromId(team.id);
  const record = `${team.record.w}–${team.record.l}`;
  const rank = `${ordinal(team.rank.current)} / ${team.rank.total}`;

  return (
    <div
      className="team-card"
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/team/${team.id}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") navigate(`/team/${team.id}`);
      }}
    >
      <div className="left">
        <div className="top-row">
          <span className="team-name">{team.name}</span>
          <PlatformPill platform={platform} />
          {team.is_live && <span className="live-dot" />}
        </div>
        <div className="score">
          <span
            {...scorePulse}
            style={{ color: winning ? "var(--text)" : "var(--text-secondary)" }}
          >
            {team.current_score.toFixed(1)}
          </span>
          <span className="vs">–</span>
          <span style={{ color: winning ? "var(--text-secondary)" : "var(--text)" }}>
            {team.current_opp_score.toFixed(1)}
          </span>
        </div>
        <div className="sub">
          <span>vs {team.current_opponent_name}</span>
          <span style={{ color: "var(--separator)" }}>•</span>
          <span>{record}</span>
          <span style={{ color: "var(--separator)" }}>•</span>
          <span>{rank}</span>
        </div>
      </div>
      <div className="spark">
        <Sparkline
          data={team.spark_last_6}
          width={140}
          height={56}
          color={team.accent_color}
          dots
          area
        />
      </div>
    </div>
  );
}
