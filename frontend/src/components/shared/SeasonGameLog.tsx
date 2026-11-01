// The player card's Game Log tab: the current season week by week, modeled on Yahoo's
// game log — opponent with its rank against the position, projection, fantasy points,
// and the stats a manager reads a week by, each shaded against the player's own average.
//
// Every regular-season week gets a row, played or not: a bye says BYE, a week he sat says
// DNP, and the weeks ahead show whom he faces and what he's projected for, so the table
// answers "how has he done" and "what's coming" in one read.

import type {
  GameLogColumn,
  PlayerStatsData,
  Position,
  SeasonLog,
  SeasonLogWeek,
} from "../../types/api";
import {
  averagesFor,
  matchupTier,
  ordinal,
  toneFor,
  type Averages,
  type Tone,
} from "./gameLogTone";

import "../../styles/player-game-log.css";

const POSITION_PLURAL: Record<Position, string> = {
  QB: "QBs",
  RB: "RBs",
  WR: "WRs",
  TE: "TEs",
  K: "Ks",
  DST: "D/STs",
};

const TONE_LABEL: Record<Tone, string> = {
  above: "above his average",
  typical: "typical for him",
  below: "below his average",
};

function fmtPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(2);
}

/** Counts print bare (`8`), anything fractional to one place (`6.8`). */
function fmtStat(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function Dash() {
  return <span className="pgl-cell pgl-empty">—</span>;
}

/** A shaded cell. The tone is in the color AND in text for a screen reader. */
function ToneCell({ text, tone }: { text: string; tone: Tone }) {
  return (
    <span className={`pgl-cell pgl-${tone}`} data-tone={tone}>
      {text}
      <span className="pgl-sr"> ({TONE_LABEL[tone]})</span>
    </span>
  );
}

function OpponentCell({ week, log }: { week: SeasonLogWeek; log: SeasonLog }) {
  if (week.state === "bye") return <span className="pgl-bye">BYE</span>;
  if (!week.opponent) return <>—</>;
  const tier =
    week.opponent_rank !== null && log.ranked_teams > 0
      ? matchupTier(week.opponent_rank, log.ranked_teams)
      : null;
  return (
    <span className={tier ? `pgl-opp-${tier}` : undefined} data-tier={tier ?? undefined}>
      {week.home === false ? "@" : ""}
      {week.opponent}
      {week.opponent_rank !== null ? ` (${ordinal(week.opponent_rank)})` : ""}
    </span>
  );
}

function PointsCell({ week, averages }: { week: SeasonLogWeek; averages: Averages }) {
  if (week.state === "dnp") return <span className="pgl-cell pgl-empty">DNP</span>;
  if (week.fantasy_points === null) return <Dash />;
  const text = fmtPoints(week.fantasy_points);
  if (week.state !== "final" || averages.fantasy_points === null) {
    return <span className="pgl-cell pgl-live">{text}</span>;
  }
  return <ToneCell text={text} tone={toneFor(week.fantasy_points, averages.fantasy_points)} />;
}

function StatCell({
  week,
  column,
  averages,
}: {
  week: SeasonLogWeek;
  column: GameLogColumn;
  averages: Averages;
}) {
  const value = week.stats?.[column.key];
  if (value === undefined || value === null) return <Dash />;
  const average = averages.stats[column.key];
  if (week.state !== "final" || average === undefined) {
    return <span className="pgl-cell pgl-live">{fmtStat(value)}</span>;
  }
  return <ToneCell text={fmtStat(value)} tone={toneFor(value, average, column.lower_is_better)} />;
}

export interface SeasonGameLogProps {
  data: PlayerStatsData;
  formatLabel: string;
}

export function SeasonGameLog({ data, formatLabel }: SeasonGameLogProps) {
  const log = data.season_log;
  if (!log) {
    return (
      <p className="muted pstats-empty">
        {data.sleeper_id
          ? "No game log for this season yet."
          : "No game log available for this player."}
      </p>
    );
  }
  const averages = averagesFor(log.weeks, log.columns);
  const plural = POSITION_PLURAL[data.position_group];

  return (
    <section className="pgl" aria-label="Week-by-week game log">
      <div className="pgl-scroll">
        <table className="pgl-table">
          <thead>
            <tr>
              <th scope="col" className="pgl-sticky pgl-wk">
                Wk
              </th>
              <th scope="col" className="pgl-sticky pgl-opp">
                Opp <span className="pgl-vs">(vs {plural})</span>
              </th>
              <th scope="col">Proj Pts</th>
              <th scope="col">Fan Pts</th>
              {log.columns.map((c) => (
                <th key={c.key} scope="col">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {log.weeks.map((week) => (
              <tr key={week.week} className={`pgl-row-${week.state}`} data-state={week.state}>
                <th scope="row" className="pgl-sticky pgl-wk">
                  {week.week}
                  {week.state === "live" && (
                    <span className="pgl-live-dot" role="img" aria-label="in progress" />
                  )}
                </th>
                <td className="pgl-sticky pgl-opp">
                  <OpponentCell week={week} log={log} />
                </td>
                <td>
                  {week.proj_points === null ? (
                    <Dash />
                  ) : (
                    <span className="pgl-cell pgl-proj">{fmtPoints(week.proj_points)}</span>
                  )}
                </td>
                <td>
                  <PointsCell week={week} averages={averages} />
                </td>
                {log.columns.map((c) => (
                  <td key={c.key}>
                    <StatCell week={week} column={c} averages={averages} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="pstats-footnote">
        {log.season} regular season. Fan Pts in {formatLabel} (Sportradar via Sleeper); Proj Pts by
        Rotowire.
        {log.ranked_teams > 0
          ? ` Opponent rank is fantasy points allowed to ${plural} per game through week ${log.ranks_through_week} — 1st allows the most.`
          : " Opponent ranks appear once a week is complete."}
      </p>

      <div className="pgl-legend" data-testid="game-log-legend">
        <span className="pgl-legend-title">Compared to Player&rsquo;s Average</span>
        <span className="pgl-legend-item">
          <span className="pgl-swatch pgl-above" aria-hidden="true" />
          Above
        </span>
        <span className="pgl-legend-item">
          <span className="pgl-swatch pgl-typical" aria-hidden="true" />
          Typical
        </span>
        <span className="pgl-legend-item">
          <span className="pgl-swatch pgl-below" aria-hidden="true" />
          Below
        </span>
      </div>
    </section>
  );
}
