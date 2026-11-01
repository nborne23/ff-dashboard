// Scores: every NFL game of a week, modeled on Sleeper's scoreboard.
//
// The week is the app's one shared week (`stores/ui.ts`), so this strip and the Topbar's
// arrows are the same control seen twice rather than two weeks that can disagree. Until
// the user picks one, the screen asks the server for ESPN's current week — the fantasy
// leagues' week can lag it by a day around the Tuesday rollover.

import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useScoresWeek, type ScoreGame } from "../../api/scores";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { Skeleton } from "../../components/primitives";
import { useUiStore } from "../../stores/ui";
import { groupByDay, statusLabel, winnerSide } from "./format";
import { TeamMark, WeekStrip } from "./parts";

import "../../styles/scores.css";

function TeamLine({ game, side }: { game: ScoreGame; side: "away" | "home" }) {
  const team = game[side];
  const winner = winnerSide(game);
  const dimmed = winner !== null && winner !== side;
  return (
    <div className={"sc-team-line" + (dimmed ? " dimmed" : "")}>
      <TeamMark team={team} size={30} />
      <span className="sc-team-name">{team.name}</span>
      {team.record && <span className="sc-team-record">{team.record}</span>}
      {game.possession === team.abbr && (
        <span className="sc-possession" aria-label="Has the ball" />
      )}
      <span className="sc-team-score">{team.score ?? ""}</span>
      <span className="sc-winner-mark" aria-label={winner === side ? "Winner" : undefined}>
        {winner === side ? "◀" : ""}
      </span>
    </div>
  );
}

function GameRow({ game, week }: { game: ScoreGame; week: number }) {
  const performer = game.top_performer;
  return (
    <Link
      to={`/scores/game/${game.game_id}?week=${week}`}
      className="sc-game"
      data-state={game.state}
      data-testid={`score-game-${game.game_id}`}
    >
      <div className="sc-game-teams">
        <TeamLine game={game} side="away" />
        <TeamLine game={game} side="home" />
      </div>
      <div className="sc-game-info">
        <div className="sc-game-status" data-state={game.state}>
          {statusLabel(game)}
        </div>
        {game.state === "in" && game.down_distance && (
          <div className="sc-game-situation">{game.down_distance}</div>
        )}
        {game.state === "pre" && game.broadcast && (
          <div className="sc-game-broadcast">{game.broadcast}</div>
        )}
        {performer && (
          <div className="sc-performer">
            {performer.headshot_url && (
              <img
                className="sc-performer-headshot"
                src={performer.headshot_url}
                alt=""
                loading="lazy"
              />
            )}
            <div className="sc-performer-text">
              <div className="sc-performer-name">{performer.short_name}</div>
              <div className="sc-performer-line">{performer.stat_line}</div>
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}

function ScoresSkeleton() {
  return (
    <div data-testid="scores-loading">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} height={112} radius={18} style={{ marginBottom: 12 }} />
      ))}
    </div>
  );
}

export default function Scores() {
  const queryClient = useQueryClient();
  const storeWeek = useUiStore((s) => s.week);
  const weekPinned = useUiStore((s) => s.weekPinned);
  const setWeek = useUiStore((s) => s.setWeek);

  const query = useScoresWeek(weekPinned ? storeWeek : null);
  const data = query.data?.data;

  const header = (
    <>
      <h1 className="large-title">Scores</h1>
      <p className="large-subtitle">
        NFL{data?.season ? ` · ${data.season}` : ""}
        {data ? ` · Week ${data.week}` : ""}
      </p>
    </>
  );

  if (query.isError) {
    return (
      <>
        {header}
        <ErrorCard
          error={query.error}
          fallbackMessage="Couldn't load the scores."
          onRetry={() => void queryClient.invalidateQueries({ queryKey: ["live_nfl_games"] })}
          testId="scores-error"
        />
      </>
    );
  }

  if (!data) {
    return (
      <>
        {header}
        <ScoresSkeleton />
      </>
    );
  }

  const days = groupByDay(data.games);

  return (
    <div className="sc-screen" data-testid="scores">
      {header}
      <WeekStrip
        weeks={data.weeks}
        selected={data.week}
        current={data.current_week}
        onSelect={setWeek}
      />

      {data.games.length === 0 ? (
        <div className="card sc-empty" data-testid="scores-empty">
          {data.fetched_at === null
            ? `Week ${data.week}'s schedule hasn't been fetched yet. It fills in within a few minutes of the server starting.`
            : `No games in week ${data.week}.`}
        </div>
      ) : (
        days.map((day) => (
          <section key={day.key} className="sc-day" aria-label={day.label}>
            <h2 className="sc-day-label">{day.label}</h2>
            {day.games.map((game) => (
              <GameRow key={game.game_id} game={game} week={data.week} />
            ))}
          </section>
        ))
      )}

      {data.byes.length > 0 && <p className="sc-byes">On bye: {data.byes.join(", ")}</p>}
    </div>
  );
}
