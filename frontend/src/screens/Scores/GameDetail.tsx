// One NFL game, modeled on Sleeper's game screen: the week's games in a strip across the
// top, a big score header, the linescore, and AWAY | FANTASY | HOME tabs.

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useScoreGame, useScoresWeek, type ScoreGame, type ScoreTeam } from "../../api/scores";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { IconArrowL, Skeleton } from "../../components/primitives";
import { useScoresStore } from "../../stores/scores";
import { useUiStore } from "../../stores/ui";
import { BoxScore } from "./BoxScore";
import { FantasyTab } from "./FantasyTab";
import { statusLabel, winnerSide } from "./format";
import { TeamMark } from "./parts";

import "../../styles/scores.css";

type Tab = "away" | "fantasy" | "home";

function GameStrip({
  games,
  selectedId,
  week,
}: {
  games: ScoreGame[];
  selectedId: string;
  week: number;
}) {
  return (
    <div className="sc-strip" aria-label="This week's games">
      <Link to="/scores" className="sc-strip-back" aria-label="All scores">
        <IconArrowL size={18} />
      </Link>
      {games.map((game) => (
        <Link
          key={game.game_id}
          to={`/scores/game/${game.game_id}?week=${week}`}
          replace
          className={"sc-strip-game" + (game.game_id === selectedId ? " selected" : "")}
          aria-current={game.game_id === selectedId ? "page" : undefined}
          data-state={game.state}
        >
          <TeamMark team={game.away} size={24} />
          <span className="sc-strip-score">{game.away.score ?? ""}</span>
          <span className="sc-strip-status">{statusLabel(game, { short: true })}</span>
          <span className="sc-strip-score">{game.home.score ?? ""}</span>
          <TeamMark team={game.home} size={24} />
        </Link>
      ))}
    </div>
  );
}

function HeaderSide({ team, side }: { team: ScoreTeam; side: "away" | "home" }) {
  return (
    <div className={`sc-hdr-side sc-hdr-${side}`}>
      <span
        className="sc-hdr-watermark"
        aria-hidden="true"
        style={team.color ? { color: `#${team.color}` } : undefined}
      >
        {team.abbr}
      </span>
      <div className="sc-hdr-name">{team.name}</div>
      <div className="sc-hdr-record">{team.record ?? ""}</div>
    </div>
  );
}

function GameHeader({ game }: { game: ScoreGame }) {
  const winner = winnerSide(game);
  return (
    <div className="sc-hdr" data-state={game.state}>
      <HeaderSide team={game.away} side="away" />
      <div className="sc-hdr-score">{game.away.score ?? ""}</div>
      <div className="sc-hdr-status" data-state={game.state}>
        {winner === "away" && <span aria-hidden="true">◀ </span>}
        {statusLabel(game, { short: true })}
        {winner === "home" && <span aria-hidden="true"> ▶</span>}
        {game.state === "pre" && game.broadcast && (
          <div className="sc-hdr-broadcast">{game.broadcast}</div>
        )}
        {game.state === "in" && game.down_distance && (
          <div className="sc-hdr-broadcast">
            {game.possession ? `${game.possession} ball · ` : ""}
            {game.down_distance}
          </div>
        )}
      </div>
      <div className="sc-hdr-score">{game.home.score ?? ""}</div>
      <HeaderSide team={game.home} side="home" />
    </div>
  );
}

function Linescore({ game }: { game: ScoreGame }) {
  const periods = Math.max(4, game.away.linescores.length, game.home.linescores.length);
  const labels = Array.from({ length: periods }, (_, i) =>
    i < 4 ? `Q${i + 1}` : periods === 5 ? "OT" : `OT${i - 3}`,
  );
  const row = (team: ScoreTeam) => (
    <tr key={team.abbr}>
      <th scope="row">
        <span className="sc-ls-team">
          <TeamMark team={team} size={22} />
          {team.abbr}
        </span>
      </th>
      {labels.map((label, i) => (
        <td key={label} className="num">
          {team.linescores[i] ?? (game.state === "pre" ? "" : "–")}
        </td>
      ))}
      <td className="num sc-ls-total">{team.score ?? ""}</td>
    </tr>
  );
  return (
    <table className="sc-linescore" data-testid="linescore">
      <thead>
        <tr>
          <th scope="col">Team</th>
          {labels.map((label) => (
            <th key={label} scope="col" className="num">
              {label}
            </th>
          ))}
          <th scope="col" className="num">
            TOT
          </th>
        </tr>
      </thead>
      <tbody>
        {row(game.away)}
        {row(game.home)}
      </tbody>
    </table>
  );
}

export default function GameDetailScreen() {
  const { gameId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const weekParam = Number(searchParams.get("week")) || null;
  const queryClient = useQueryClient();
  const leagueId = useScoresStore((s) => s.leagueId);
  const setLeagueId = useScoresStore((s) => s.setLeagueId);
  const [tab, setTab] = useState<Tab>("fantasy");
  const setWeek = useUiStore((s) => s.setWeek);
  const setPickedWeek = useScoresStore((s) => s.setPickedWeek);

  const gameQuery = useScoreGame(gameId, leagueId, weekParam);
  const detail = gameQuery.data?.data;
  const weekQuery = useScoresWeek(detail?.week ?? weekParam);
  const games = weekQuery.data?.data.games ?? [];
  // The list is fresher than the detail between polls; prefer its copy of this game.
  const game = games.find((g) => g.game_id === gameId) ?? detail?.game;

  // The Topbar names this game's week, and "back to all scores" returns to it.
  const detailWeek = detail?.week;
  useEffect(() => {
    if (detailWeek === undefined) return;
    setWeek(detailWeek);
    setPickedWeek(detailWeek);
  }, [detailWeek, setWeek, setPickedWeek]);

  if (gameQuery.isError) {
    return (
      <ErrorCard
        error={gameQuery.error}
        fallbackMessage="Couldn't load this game."
        onRetry={() => void queryClient.invalidateQueries({ queryKey: ["live_nfl_games"] })}
        testId="game-error"
      />
    );
  }

  if (!detail || !game) {
    return (
      <div data-testid="game-loading">
        <Skeleton height={44} radius={22} style={{ marginBottom: 16 }} />
        <Skeleton height={120} radius={18} style={{ marginBottom: 16 }} />
        <Skeleton height={320} radius={18} />
      </div>
    );
  }

  const tabs: { id: Tab; label: string; team?: ScoreTeam }[] = [
    { id: "away", label: game.away.name, team: game.away },
    { id: "fantasy", label: "Fantasy" },
    { id: "home", label: game.home.name, team: game.home },
  ];

  return (
    <div className="sc-screen sc-detail" data-testid="game-detail">
      <GameStrip games={games.length ? games : [game]} selectedId={gameId} week={detail.week} />
      <GameHeader game={game} />
      <Linescore game={game} />

      <div className="sc-tabs" role="tablist" aria-label="Game view">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            aria-label={t.label}
            className={"sc-tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.team && <TeamMark team={t.team} size={20} />}
            {t.team ? (
              <>
                <span className="sc-tab-full">{t.label}</span>
                <span className="sc-tab-abbr" aria-hidden="true">
                  {t.team.abbr}
                </span>
              </>
            ) : (
              t.label
            )}
          </button>
        ))}
      </div>

      {tab === "fantasy" ? (
        <FantasyTab detail={detail} onLeagueChange={setLeagueId} />
      ) : (
        <BoxScore detail={detail} side={tab} />
      )}
    </div>
  );
}
