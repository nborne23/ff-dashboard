// Task 3.11 — the 3-5 shortlist at the TOP of the screen (Draft/index.tsx renders this
// before the board/roster grid), one-line reasons, and inspectable cited heuristics
// (`fired_rule_ids`, expandable per card rather than always-on clutter). Tier-break
// alarms render as their own prominent banner (position/count/picks-until-turn, exactly
// what `draft_recommender.tier_break_alarms` returns). Turn pairs (back-to-back picks,
// e.g. 24/25) are shown as a pair, side by side -- never flattened into two independent
// single-pick recommendations, which would lose the "don't double up a 1-QB league"
// pairing logic `recommend_pair` already applied server-side.

import { useState } from "react";

import type { RecommendationOut } from "../../api/draft";
import { useDraftRecommendations } from "../../api/draft";
import { Skeleton } from "../../components/primitives";
import { ErrorCard } from "../../components/shared/ErrorCard";

function RecommendationCard({
  rec,
  highlight = false,
}: {
  rec: RecommendationOut;
  highlight?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={"rec-card" + (highlight ? " top-pick" : "")}>
      <div className="rec-header">
        <span className="player-name">{rec.candidate.name}</span>
        <span className="pill pos">{rec.candidate.position}</span>
        <span className="rec-score">{rec.score.toFixed(1)}</span>
      </div>
      <div className="rec-reason">{rec.reason}</div>
      <button
        type="button"
        className="btn"
        style={{ marginTop: 8, fontSize: 12, padding: "4px 10px" }}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? "Hide cited rules" : "Why?"}
      </button>
      {expanded && (
        <div className="rec-rules">
          {rec.fired_rule_ids.map((id) => (
            <span key={id} className="pill bench">
              {id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function Recommendations() {
  const recQuery = useDraftRecommendations();

  if (recQuery.isError) {
    return (
      <ErrorCard
        error={recQuery.error}
        fallbackMessage="Couldn't load recommendations."
        onRetry={() => void recQuery.refetch()}
        testId="recommendations-error"
      />
    );
  }

  if (recQuery.isLoading || !recQuery.data) {
    return (
      <div className="card" data-testid="recommendations-skeleton" aria-hidden="true">
        <Skeleton width="30%" height={20} />
        <div style={{ height: 10 }} />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={64} style={{ marginBottom: 8 }} />
        ))}
      </div>
    );
  }

  const data = recQuery.data.data;

  return (
    <div data-testid="recommendations">
      {data.positional_runs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {data.positional_runs.map((run) => (
            <div key={run.position} className="positional-run-banner" data-testid="positional-run">
              {run.position} run in progress — {run.count} of the last 8 picks.
            </div>
          ))}
        </div>
      )}

      {data.tier_alarms.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {data.tier_alarms.map((alarm) => (
            <div key={`${alarm.position}-${alarm.tier}`} className="tier-alarm">
              Tier {alarm.tier} {alarm.position} down to {alarm.remaining} left —{" "}
              {alarm.picks_until_next} picks until your turn.
            </div>
          ))}
        </div>
      )}

      {data.turn_pairs.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div className="section-label" style={{ fontSize: 14, marginBottom: 8 }}>
            Back-to-back: picks {data.turn_pairs[0].pick_a} &amp; {data.turn_pairs[0].pick_b}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data.turn_pairs.map((pair, i) => (
              <div
                key={i}
                style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}
                data-testid="turn-pair"
              >
                <RecommendationCard rec={pair.recommendation_a} />
                <RecommendationCard rec={pair.recommendation_b} />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="section-label" style={{ fontSize: 16 }}>
        Top Picks
      </div>
      {data.shortlist.length === 0 ? (
        <p className="muted">
          {data.picks_until_next === null ? "Draft complete." : "No recommendations yet."}
        </p>
      ) : (
        <div className="rec-shortlist">
          {data.shortlist.map((rec, i) => (
            <RecommendationCard key={rec.candidate.name} rec={rec} highlight={i === 0} />
          ))}
        </div>
      )}

      {data.advisories.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 16 }}>
          {data.advisories.map((advisory, i) => (
            <p key={i} className="muted" style={{ fontSize: 13, margin: 0 }}>
              {advisory}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
