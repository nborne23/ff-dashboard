// Ported from design/screen-dashboard.jsx's InsightLiveGames. Fed by
// useLiveNflGames(), a typed stub until GET /api/nfl/scoreboard exists
// (Phase 8 — see frontend/src/api/liveNflGames.ts). Until then this renders
// the card's "no games" state.

import { IconFlame } from "../../components/primitives";
import { useLiveNflGames } from "../../api/liveNflGames";
import type { LiveNflGame } from "../../types/api";

function statusText(game: LiveNflGame): string {
  if (game.state === "post") return "FINAL";
  if (game.state === "postponed") return "POSTPONED";
  if (game.state === "pre") {
    const kickoff = new Date(game.kickoff_at);
    return Number.isNaN(kickoff.getTime())
      ? "Scheduled"
      : kickoff.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  }
  const period = game.period != null ? `Q${game.period}` : "Live";
  return game.clock ? `${period} ${game.clock}` : period;
}

function GameRow({ game }: { game: LiveNflGame }) {
  const isLive = game.state === "in";
  const showScore = game.state === "in" || game.state === "post";
  const status = statusText(game);

  return (
    <div className="game-row">
      <div>
        <div className="matchup">
          <span className="num">{game.away_team}</span> @{" "}
          <span className="num">{game.home_team}</span>
        </div>
        <div
          style={{
            fontSize: 11,
            color: isLive ? "var(--live)" : "var(--text-secondary)",
            marginTop: 1,
            fontWeight: 600,
          }}
        >
          {isLive && (
            <span
              style={{
                display: "inline-block",
                width: 5,
                height: 5,
                borderRadius: "50%",
                background: "var(--live)",
                marginRight: 4,
                verticalAlign: "middle",
                boxShadow: "0 0 6px var(--live)",
              }}
            />
          )}
          {status}
        </div>
      </div>
      {showScore && (
        <div className="gscore tnum">
          {game.away_score}–{game.home_score}
        </div>
      )}
    </div>
  );
}

export function InsightLiveGames() {
  const { games, isLoading } = useLiveNflGames();
  const activeCount = games.filter((g) => g.state === "in").length;

  return (
    <div className="card">
      <div className="card-header">
        <span className="cat-dot" style={{ background: "var(--live)" }}>
          <IconFlame size={9} />
        </span>
        <span className="cat-label" style={{ color: "var(--live)" }}>
          Live Games
        </span>
        <span className="ts">{activeCount} active</span>
      </div>

      {!isLoading && games.length === 0 && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)", padding: "12px 0" }}>
          No live games
        </div>
      )}

      {games.map((game) => (
        <GameRow key={game.nfl_game_id} game={game} />
      ))}
    </div>
  );
}
