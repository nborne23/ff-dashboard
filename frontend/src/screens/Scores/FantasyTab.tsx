// A game's Fantasy tab, laid out like Sleeper's: one section per position, away players
// down the left and home players down the right, each with fantasy points over the
// projection, and a league picker that decides whose scoring the points are in.

import { useState } from "react";

import type { FantasyGroup, FantasyPlayer, GameDetail, ScoringLeague } from "../../api/scores";
import { PlayerStatsPanel } from "../../components/shared/PlayerStatsPanel";
import { formatPoints } from "./format";

const FORMAT_LABEL: Record<GameDetail["points_format"], string> = {
  ppr: "PPR",
  half_ppr: "Half PPR",
  standard: "Standard",
};

/** The short name as a button that opens the player's stats card — when we have a card
 *  for him. Most of a depth chart isn't in any of the user's leagues, so has none. */
function PlayerTitle({
  player,
  teamId,
  week,
}: {
  player: FantasyPlayer;
  teamId: string | undefined;
  week: number;
}) {
  const [open, setOpen] = useState(false);
  if (!player.player) return <span className="sc-fp-name">{player.short_name}</span>;
  return (
    <>
      <button
        type="button"
        className="sc-fp-name player-name-button"
        aria-haspopup="dialog"
        aria-label={player.name}
        onClick={() => setOpen(true)}
      >
        {player.short_name}
      </button>
      {open && (
        <PlayerStatsPanel
          player={player.player}
          teamId={teamId}
          week={week}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function StatLine({ player }: { player: FantasyPlayer }) {
  if (player.stat_line.length === 0) return null;
  return (
    <div className="sc-fp-line">
      {player.stat_line.map((token, i) => (
        <span key={i} className="sc-fp-token">
          {token.value} <span className="sc-fp-token-label">{token.label}</span>
          {i < player.stat_line.length - 1 ? ", " : ""}
        </span>
      ))}
    </div>
  );
}

function PlayerCell({
  player,
  side,
  teamId,
  week,
}: {
  player: FantasyPlayer | undefined;
  side: "away" | "home";
  teamId: string | undefined;
  week: number;
}) {
  if (!player) return <div className={`sc-fp sc-fp-${side}`} />;
  return (
    <div
      className={`sc-fp sc-fp-${side}` + (player.is_mine ? " mine" : "")}
      data-testid={`fp-${player.sleeper_id}`}
    >
      <PlayerTitle player={player} teamId={teamId} week={week} />
      <div className="sc-fp-meta">
        <span className={`sc-pos-text sc-pos-${player.position}`}>{player.position}</span>
        <span aria-hidden="true"> • </span>
        {player.team}
      </div>
      {player.fantasy_team && (
        <div className={"sc-fp-owner" + (player.is_mine ? " mine" : "")}>
          {player.is_mine ? "Your team" : player.fantasy_team}
        </div>
      )}
      <StatLine player={player} />
    </div>
  );
}

function PointsCell({
  player,
  side,
}: {
  player: FantasyPlayer | undefined;
  side: "away" | "home";
}) {
  if (!player) return <div className={`sc-fpts sc-fpts-${side}`} />;
  return (
    <div className={`sc-fpts sc-fpts-${side}`}>
      <div
        className="sc-fpts-points"
        title={
          player.source === "league" ? "This league's own score" : "Estimated from the stat line"
        }
      >
        {formatPoints(player.points)}
      </div>
      <div className="sc-fpts-proj">{formatPoints(player.projection)}</div>
    </div>
  );
}

function PositionSection({
  group,
  teamId,
  week,
}: {
  group: FantasyGroup;
  teamId: string | undefined;
  week: number;
}) {
  const rows = Math.max(group.away.length, group.home.length);
  return (
    <section className="sc-pos-section" aria-label={group.position}>
      <div className="sc-pos-divider">
        <span className={`sc-pos-chip sc-pos-${group.position}`}>{group.position}</span>
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="sc-fp-row">
          <PlayerCell player={group.away[i]} side="away" teamId={teamId} week={week} />
          <PointsCell player={group.away[i]} side="away" />
          <PointsCell player={group.home[i]} side="home" />
          <PlayerCell player={group.home[i]} side="home" teamId={teamId} week={week} />
        </div>
      ))}
    </section>
  );
}

export interface FantasyTabProps {
  detail: GameDetail;
  onLeagueChange: (leagueId: string) => void;
}

export function FantasyTab({ detail, onLeagueChange }: FantasyTabProps) {
  const league: ScoringLeague | undefined = detail.leagues.find(
    (lg) => lg.league_id === detail.league_id,
  );
  const teamId = league?.team_id ?? undefined;

  return (
    <div className="sc-fantasy" data-testid="fantasy-tab">
      <div className="sc-fantasy-head">
        <span className="sc-fantasy-label">Fantasy Leagues</span>
        {detail.leagues.length > 0 ? (
          <div className="sc-league-picker">
            <select
              aria-label="Score with league"
              value={detail.league_id ?? ""}
              onChange={(event) => onLeagueChange(event.target.value)}
              data-testid="league-picker"
            >
              {detail.leagues.map((lg) => (
                <option key={lg.league_id} value={lg.league_id}>
                  {lg.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span className="sc-fantasy-format">{FORMAT_LABEL[detail.points_format]}</span>
        )}
      </div>
      <p className="sc-fantasy-note">
        {detail.points_format_fallback
          ? "This league uses custom scoring. Players on its rosters show its own points; everyone else is a PPR estimate."
          : `${FORMAT_LABEL[detail.points_format]} scoring. Players on this league's rosters show its own points.`}
      </p>

      {detail.groups.length === 0 ? (
        <div className="sc-empty-inline" data-testid="fantasy-empty">
          {detail.game.state === "pre"
            ? "Projections for this game haven't been fetched yet."
            : "No stat lines for this game yet."}
        </div>
      ) : (
        detail.groups.map((group) => (
          <PositionSection key={group.position} group={group} teamId={teamId} week={detail.week} />
        ))
      )}
    </div>
  );
}
