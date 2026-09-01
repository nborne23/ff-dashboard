// Ported from design/screen-dashboard.jsx's TeamCard — DOM structure and
// classNames match verbatim so global.css's `.team-card` rules apply
// unmodified. Team.platform isn't a field on the normalized Team entity
// (per design.md D12); it's derived from the `{platform}:{platform_id}`
// stable id (specs/fantasy-data-model/spec.md, "Stable internal id").

import { TeamLogo } from "../../components/shared/TeamLogo";
import { useNavigate } from "react-router-dom";

import { Sparkline } from "../../components/primitives";
import { useChangedValuePulse } from "../../hooks/useChangedValuePulse";
import { platformFromId } from "../../types/api";
import type { Platform, Team } from "../../types/api";
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
        {/* The name owns this row outright. Both badges that used to share it — the
            platform pill and then the logo — were taking width from a column that is
            only ~95px wide on desktop, where the team names need 83–149px. The logo
            moved to the right column instead (see below); the pill's information now
            rides on that logo as a ring. */}
        <div className="top-row">
          <span className="team-name">{team.name}</span>
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
      {/* Logo here rather than in a leading avatar column. A column on the left looks
          like the obvious layout but is strictly worse: the card's content box is
          fixed, so a 40px column plus its gap comes straight out of the name's width
          (95px -> 75px on desktop). This column is 140px and mostly whitespace above
          the sparkline, so the logo is free here — and at 40px it is the largest and
          most legible avatar in the app. */}
      <div className="spark">
        <TeamLogo
          team={team}
          size={40}
          ringColor={platform === "yahoo" ? "var(--yahoo)" : "var(--espn)"}
        />
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
