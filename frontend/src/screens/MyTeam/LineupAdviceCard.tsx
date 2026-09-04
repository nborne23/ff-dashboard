// Start/sit advice: the optimal legal lineup and the swaps that reach it.
//
// The card's job is to be ignorable. Most weeks a lineup is already optimal, and a
// panel that manufactures something to say on those weeks trains the user to stop
// reading it — so "no changes" is a first-class, quiet state, and the card only raises
// its voice when there is a real move to make.
//
// Three states carry genuinely different meanings and must not collapse into one:
//   - no advice available  -> we couldn't evaluate (unsynced roster / job never ran)
//   - no moves             -> we evaluated and your lineup is right
//   - moves                -> here is what to change

import type { LineupAdvice, LineupMove } from "../../types/api";

function MoveRow({ move }: { move: LineupMove }) {
  return (
    <li className="lineup-move" data-reason={move.reason}>
      <div className="lineup-move-slot">{move.slot}</div>
      <div className="lineup-move-swap">
        <div className="lineup-move-line">
          <span className="lineup-move-verb sit">SIT</span>
          <span className="player-name">{move.out_player.name}</span>
          <span className="muted lineup-move-pts">{move.out_points.toFixed(1)}</span>
          <span className="lineup-move-src">RW</span>
          {move.reason === "unstartable" && (
            <span className="pill inj inj-o" title="Cannot play this week">
              OUT
            </span>
          )}
        </div>
        <div className="lineup-move-line">
          <span className="lineup-move-verb start">START</span>
          <span className="player-name">{move.in_player.name}</span>
          <span className="muted lineup-move-pts">{move.in_points.toFixed(1)}</span>
          <span className="lineup-move-src">RW</span>
        </div>
      </div>
      <div className="lineup-move-gain">
        <span className="delta pos">+{move.delta.toFixed(1)}</span>
        {/* Two unrelated projections agreeing is worth more than either one's margin,
            so it is called out on the move rather than buried in a tooltip. */}
        {move.consensus && (
          <span className="lineup-consensus" title="Both projection sources agree">
            ✓ both sources
          </span>
        )}
      </div>
    </li>
  );
}

export interface LineupAdviceCardProps {
  advice: LineupAdvice;
}

export function LineupAdviceCard({ advice }: LineupAdviceCardProps) {
  const sourceLabel = advice.source === "rotowire" ? "Rotowire" : "your league platform";

  if (!advice.advice_available) {
    return (
      <div className="card lineup-card" data-testid="lineup-advice">
        <div className="lineup-head">
          <span className="section-label">Start / Sit</span>
        </div>
        <p className="muted lineup-empty">
          No projections to work from yet. They arrive with the next data refresh.
        </p>
      </div>
    );
  }

  return (
    <div className="card lineup-card" data-testid="lineup-advice">
      <div className="lineup-head">
        <span className="section-label">Start / Sit</span>
        <span className="muted lineup-source">by {sourceLabel}</span>
      </div>

      {advice.moves.length === 0 ? (
        <>
          <p className="lineup-optimal" data-testid="lineup-optimal">
            Your lineup is optimal.
          </p>
          {advice.comparison_available && advice.sources_agree && (
            <p className="muted lineup-empty">Both projection sources agree.</p>
          )}
        </>
      ) : (
        <>
          <div className="lineup-gain-row">
            <span className="lineup-gain">+{advice.gain.toFixed(1)}</span>
            <span className="muted">
              projected points from {advice.moves.length}{" "}
              {advice.moves.length === 1 ? "change" : "changes"}
            </span>
          </div>
          <ul className="lineup-moves">
            {advice.moves.map((m) => (
              <MoveRow key={m.slot + m.in_player.id} move={m} />
            ))}
          </ul>
        </>
      )}

      {advice.unevaluated.length > 0 && (
        // Named rather than silently dropped: a player with no projection is never
        // promoted, and the user should know which players the advice couldn't see.
        <p className="muted lineup-empty">
          Not evaluated (no {sourceLabel} projection):{" "}
          {advice.unevaluated.map((p) => p.name).join(", ")}
        </p>
      )}
    </div>
  );
}
