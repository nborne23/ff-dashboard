// Task 6.3 — full scouting content for a board player, opened from a tap on a board
// row (BoardList.tsx). Backend source: `GET /api/draft/board`'s `BoardPlayerOut`
// (backend/gridiron/schemas/draft.py), extended in this same phase to carry
// sleeper_category/catalyst/format_fit/injury_tags/analyst_takes/tier labels that
// were already loaded but not exposed before.
//
// Two things this panel is deliberately careful about, per the task contract:
//   1. Each analyst take renders its `source` TOGETHER WITH `verified_accuracy` --
//      `sources.json`'s tier_a_measured (accuracy-tracked) analysts must never look
//      the same as tier_b_popular_unverified (e.g. The Fantasy Footballers, who
//      stopped submitting to FantasyPros and so carry no third-party accuracy score).
//   2. `injury_tags` are keyword-derived from note prose, not a curated injury report,
//      and are demonstrably wrong in the board data itself (Jahmyr Gibbs carries "mcl"
//      because his note mentions backup Pacheco's MCL sprain, not his own injury) --
//      so they're labelled here as a search aid over the note text, never as fact.

import type { ReactNode } from "react";

import type { BoardPlayerOut } from "../../api/draft";

export interface PlayerDetailProps {
  player: BoardPlayerOut | null;
  onClose: () => void;
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="draft-detail-section">
      <div className="section-label">{label}</div>
      {children}
    </div>
  );
}

function metaLine(player: BoardPlayerOut): string {
  const bits: string[] = [];
  if (player.nfl_team) bits.push(player.nfl_team);
  if (player.bye) bits.push(`Bye ${player.bye}`);
  if (player.adp_rank) bits.push(`ADP ${player.adp_rank}`);
  return bits.join(" · ");
}

export function PlayerDetail({ player, onClose }: PlayerDetailProps) {
  if (!player) return null;

  return (
    <div
      className="draft-detail-overlay"
      onClick={onClose}
      data-testid="player-detail-overlay"
      role="presentation"
    >
      <div
        className="draft-detail-panel card"
        onClick={(event) => event.stopPropagation()}
        data-testid="player-detail"
        role="dialog"
        aria-modal="true"
        aria-label={`${player.name} scouting detail`}
      >
        <div className="draft-detail-header">
          <div>
            <div className="player-name" style={{ fontSize: 18, fontWeight: 700 }}>
              {player.name}
              {player.out_for_season && (
                <span className="pill loss" style={{ marginLeft: 8 }}>
                  OUT FOR SEASON
                </span>
              )}
            </div>
            <div className="player-meta">
              <span className="pill pos" style={{ marginRight: 6 }}>
                {player.position}
              </span>
              {metaLine(player)}
            </div>
          </div>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            aria-label={`Close ${player.name} detail`}
          >
            Close
          </button>
        </div>

        {(player.overall_tier_label || player.positional_tier_label) && (
          <Section label="Tiers">
            {player.overall_tier_label && (
              <p>
                Overall Tier {player.overall_tier}: {player.overall_tier_label}
              </p>
            )}
            {player.positional_tier_label && (
              <p>
                {player.position} Tier {player.positional_tier}: {player.positional_tier_label}
              </p>
            )}
          </Section>
        )}

        <Section label="Risk">
          <p>
            {player.risk ?? "Unrated"}
            {player.risk_score != null ? ` (score ${player.risk_score}/5)` : ""}
          </p>
        </Section>

        {player.thesis && (
          <Section label="Thesis">
            <p>{player.thesis}</p>
          </Section>
        )}

        {player.note && (
          <Section label="Note">
            <p>{player.note}</p>
          </Section>
        )}

        {player.take_in_round && (
          <Section label="Take By Round">
            <p>{player.take_in_round}</p>
          </Section>
        )}

        {player.sleeper_category && (
          <Section label="Sleeper Category">
            <p>{player.sleeper_category}</p>
          </Section>
        )}

        {player.catalyst && (
          <Section label="Catalyst">
            <p>{player.catalyst}</p>
          </Section>
        )}

        {player.format_fit && (
          <Section label="Format Fit">
            <p>{player.format_fit}</p>
          </Section>
        )}

        {player.analyst_takes.length > 0 && (
          <Section label="Analyst Takes">
            {player.analyst_takes.map((take, i) => (
              <div className="analyst-take" key={i} data-testid="analyst-take">
                <div className="analyst-take-source">
                  <span className="source-name">{take.source}</span>
                  <span
                    className={"pill " + (take.verified_accuracy ? "win" : "bench")}
                    data-testid="analyst-accuracy-badge"
                  >
                    {take.verified_accuracy ? "Measured accuracy" : "Unverified accuracy"}
                  </span>
                </div>
                <div className="analyst-take-take">{take.take}</div>
                {take.detail && <div className="analyst-take-detail">{take.detail}</div>}
              </div>
            ))}
          </Section>
        )}

        {player.injury_tags.length > 0 && (
          <Section label="Injury Keyword Tags">
            <p className="injury-tag-disclaimer">
              Auto-extracted keywords from this player&apos;s note text above — a search aid to jump
              to relevant prose, NOT a curated injury report. They can name the wrong player&apos;s
              injury (the note may be discussing a teammate or backup) and should never be read as a
              diagnosis on their own.
            </p>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {player.injury_tags.map((tag) => (
                <span key={tag} className="pill bench">
                  {tag}
                </span>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
