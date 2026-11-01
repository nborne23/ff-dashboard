// One pairing on the All Matchups screen: two stacked team rows, each with its standings
// position, logo, name, manager and record, and the week's score on the right.
//
// The leader's score is drawn at full strength and the trailer's dimmed, so a scan down
// the page reads who is winning without comparing digits. The user's own matchup gets
// an accent outline and a label instead of a sponsor banner.

import { Link } from "react-router-dom";

import type { LeagueMatchupEntry, LeagueMatchupSide } from "../../api/leagueMatchups";
import { TeamLogo } from "../../components/shared/TeamLogo";
import { leader, recordText } from "./format";

function SideRow({
  side,
  score,
  proj,
  leading,
  showProj,
}: {
  side: LeagueMatchupSide;
  score: number;
  proj: number;
  leading: boolean;
  showProj: boolean;
}) {
  const { team } = side;
  return (
    <div className="lm-row" data-leading={leading || undefined}>
      <span className="lm-rank">{side.position || "–"}</span>
      <TeamLogo team={team} size={40} />
      <div className="lm-team">
        <div className="lm-name" data-own={team.is_user_team || undefined}>
          {team.name}
        </div>
        <div className="lm-meta">
          {team.manager_name ? `${team.manager_name} · ` : ""}
          {recordText(team.record)}
        </div>
      </div>
      <div className="lm-score-col">
        <div className="lm-score">{score.toFixed(2)}</div>
        {showProj && <div className="lm-proj">proj {proj.toFixed(1)}</div>}
      </div>
    </div>
  );
}

export function MatchupCard({ entry, href }: { entry: LeagueMatchupEntry; href: string }) {
  const { matchup, home, away } = entry;
  const lead = leader(matchup.home_score, matchup.away_score);
  const live = home.is_live || away.is_live;
  // A projection is a forecast: once the matchup is settled it only adds noise.
  const showProj = !matchup.is_complete && (matchup.home_proj > 0 || matchup.away_proj > 0);

  const status = live ? (
    <span className="pill live">LIVE</span>
  ) : matchup.is_complete ? (
    <span className="lm-status">Final</span>
  ) : null;

  return (
    <Link
      to={href}
      className="card lm-card"
      data-own={entry.is_user_matchup || undefined}
      aria-label={`${home.team.name} ${matchup.home_score.toFixed(2)}, ${away.team.name} ${matchup.away_score.toFixed(2)}`}
    >
      {(entry.is_user_matchup || status) && (
        <div className="lm-card-head">
          {entry.is_user_matchup ? <span className="lm-own-label">Your matchup</span> : <span />}
          {status}
        </div>
      )}
      <SideRow
        side={home}
        score={matchup.home_score}
        proj={matchup.home_proj}
        leading={lead === 1}
        showProj={showProj}
      />
      <SideRow
        side={away}
        score={matchup.away_score}
        proj={matchup.away_proj}
        leading={lead === -1}
        showProj={showProj}
      />
    </Link>
  );
}
