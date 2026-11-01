// The player card behind every clickable name (add-player-stats): a headline strip, then
// three tabs modeled on Yahoo's player card —
//
// - Overview: this week's stat line and points breakdown.
// - Game Log: the current season week by week, shaded against his own average, with
//   each opponent's rank against the position and the weeks still to come.
// - Stats: every season's box scores and career totals.
//
// Same dialog shape as PlayerHealthPanel — portal, Escape, body scroll lock, the
// `.draft-detail-*` overlay — widened, because a stat table at 560px is all ellipsis.
// This card used to be one scrolling sheet; it grew tabs with the Game Log, which on its
// own is a full screen of rows. "Is this week normal for him" now lives in the Game Log's
// shading rather than in scrolling from one table to the next.

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { usePlayerStats } from "../../api/players";
import { nflTeamName } from "./nflTeamNames";
import {
  rememberPlayerCardTab,
  rememberedPlayerCardTab,
  type PlayerCardTab,
} from "./playerCardTab";
import { SeasonGameLog } from "./SeasonGameLog";
import type {
  BreakdownLine,
  GameLogRow,
  Player,
  PlayerStatsData,
  PointsFormat,
  StatColumn,
  ThisWeekStats,
} from "../../types/api";

const FORMAT_LABELS: Record<PointsFormat, string> = {
  ppr: "PPR",
  half_ppr: "Half PPR",
  standard: "Standard",
};

/** Counts print bare (`8`), anything fractional to one place (`6.8`). */
function fmtStat(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function fmtPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}

function signed(value: number): string {
  return (value > 0 ? "+" : "") + value.toFixed(2).replace(/\.?0+$/, "");
}

function Headshot({ player }: { player: Player }) {
  const [failed, setFailed] = useState(false);
  const initials = player.name
    .split(" ")
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
  return (
    <div className="headshot pstats-headshot">
      {player.headshot_url && !failed ? (
        <img src={player.headshot_url} alt="" onError={() => setFailed(true)} />
      ) : (
        initials
      )}
    </div>
  );
}

function WeekStatus({ week }: { week: ThisWeekStats }) {
  if (week.is_live) {
    return (
      <span className="pstats-status live">
        <span className="pstats-live-dot" aria-hidden="true" />
        {week.status_text || "Live"}
      </span>
    );
  }
  if (week.final) return <span className="pstats-status">Final</span>;
  if (week.status_text) return <span className="pstats-status">{week.status_text}</span>;
  return null;
}

function Breakdown({
  lines,
  total,
  source,
  format,
  final,
}: {
  lines: BreakdownLine[];
  total: number | null;
  source: ThisWeekStats["breakdown_source"];
  format: string;
  final: boolean;
}) {
  // An in-progress estimate is NOT reconciled to the league score (the two refresh on
  // different clocks), so its total is its own and says so.
  const estimateOnly = source === "estimated" && !final;
  return (
    <div className="pstats-breakdown" data-testid="points-breakdown">
      <div className="section-label">Points breakdown</div>
      <ul>
        {lines.map((line) => (
          <li key={line.label} className={line.points < 0 ? "neg" : undefined}>
            <span className="pstats-bd-label">{line.label}</span>
            <span className="pstats-bd-value muted">
              {line.stat_value === null ? "" : fmtStat(line.stat_value)}
            </span>
            <span className="pstats-bd-points">{signed(line.points)}</span>
          </li>
        ))}
        <li className="pstats-bd-total">
          <span className="pstats-bd-label">{estimateOnly ? "Estimated total" : "Total"}</span>
          <span />
          <span className="pstats-bd-points">{fmtPoints(total)}</span>
        </li>
      </ul>
      <p className="pstats-footnote">
        {source === "league"
          ? "Your league's own scoring, line by line."
          : estimateOnly
            ? `Estimated from the latest stat line with standard ${format} scoring. It can differ from your league's live score until the week is final.`
            : `Estimated with standard ${format} scoring. Anything your league scores differently is on its own line, so the total matches.`}
      </p>
    </div>
  );
}

function ThisWeek({ data }: { data: PlayerStatsData }) {
  const week = data.this_week;
  const sleeperRow = data.game_log.find((r) => r.season === week.season && r.week === week.week);
  const points = week.league_points ?? sleeperRow?.fantasy_points ?? null;
  // A pre-kickoff 0.0 reads as "was shut out"; until there's a stat line it's a dash.
  const hasPlayed = week.final || week.stats !== null;
  const statColumns = data.columns.filter((c) => week.stats && c.key in week.stats);
  const format = FORMAT_LABELS[data.points_format];

  return (
    <section className="pstats-section" aria-label={`Week ${week.week}`}>
      <div className="pstats-week-head">
        <div>
          <div className="section-label">
            Week {week.week}
            {week.opponent ? ` · vs ${week.opponent}` : ""}
          </div>
          <div className="pstats-week-points">
            <span className="pstats-score">{hasPlayed ? fmtPoints(points) : "—"}</span>
            {/* Yahoo publishes no projection and reports it as 0 — not worth printing. */}
            {week.league_proj ? (
              <span className="muted">of {week.league_proj.toFixed(1)} proj</span>
            ) : null}
          </div>
        </div>
        <WeekStatus week={week} />
      </div>

      {statColumns.length > 0 ? (
        <dl className="pstats-statline">
          {statColumns.map((c) => (
            <div key={c.key}>
              <dt>{c.label}</dt>
              <dd>{fmtStat(week.stats?.[c.key])}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted pstats-empty">
          {week.final ? "Didn't record a stat this week." : "No stats yet this week."}
        </p>
      )}

      {week.breakdown.length > 0 && (
        <Breakdown
          lines={week.breakdown}
          total={week.breakdown_total}
          source={week.breakdown_source}
          format={format}
          final={week.final}
        />
      )}
    </section>
  );
}

function totalsFor(rows: GameLogRow[], columns: StatColumn[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const c of columns) {
    const values = rows.map((r) => r.stats[c.key]).filter((v): v is number => v !== undefined);
    if (values.length === 0) continue;
    out[c.key] = c.agg === "max" ? Math.max(...values) : values.reduce((a, b) => a + b, 0);
  }
  return out;
}

function BoxScores({ data }: { data: PlayerStatsData }) {
  const seasons = data.seasons.map((s) => s.season);
  const [season, setSeason] = useState(seasons[0]);
  const rows = useMemo(
    () => data.game_log.filter((r) => r.season === season),
    [data.game_log, season],
  );
  const totals = totalsFor(rows, data.columns);
  const summary = data.seasons.find((s) => s.season === season);
  const live = data.this_week;

  return (
    <section className="pstats-section" aria-label="Box scores">
      <div className="pstats-section-head">
        <div className="section-label">Box scores</div>
        <div className="segmented pstats-seasons" role="tablist" aria-label="Season">
          {seasons.map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={s === season}
              className={s === season ? "active" : ""}
              onClick={() => setSeason(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="pstats-table-scroll">
        <table className="pstats-table">
          <thead>
            <tr>
              <th>Wk</th>
              <th className="left">Opp</th>
              {data.columns.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
              <th>FPTS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const inProgress = r.season === live.season && r.week === live.week && !live.final;
              return (
                <tr key={r.week} className={inProgress ? "in-progress" : undefined}>
                  <td>{r.week}</td>
                  <td className="left">{r.opponent ?? "—"}</td>
                  {data.columns.map((c) => (
                    <td key={c.key}>{fmtStat(r.stats[c.key])}</td>
                  ))}
                  <td className="pstats-fpts">{fmtPoints(r.fantasy_points)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} className="left">
                {summary?.games ?? 0} games
              </td>
              {data.columns.map((c) => (
                <td key={c.key}>{fmtStat(totals[c.key])}</td>
              ))}
              <td className="pstats-fpts">{fmtPoints(summary?.fantasy_points)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

function Career({ data }: { data: PlayerStatsData }) {
  return (
    <section className="pstats-section" aria-label="Career">
      <div className="section-label">By season</div>
      <div className="pstats-table-scroll">
        <table className="pstats-table">
          <thead>
            <tr>
              <th className="left">Year</th>
              <th className="left">Team</th>
              <th>GP</th>
              {data.columns.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
              <th>FPTS</th>
              <th>PPG</th>
            </tr>
          </thead>
          <tbody>
            {data.seasons.map((s) => (
              <tr key={s.season}>
                <td className="left">{s.season}</td>
                <td className="left">{s.team ?? "—"}</td>
                <td>{s.games}</td>
                {data.columns.map((c) => (
                  <td key={c.key}>{fmtStat(s.stats[c.key])}</td>
                ))}
                <td className="pstats-fpts">{fmtPoints(s.fantasy_points)}</td>
                <td>{fmtPoints(s.ppg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Season points, position rank, points per game — Yahoo's strip, minus the start and
 *  roster percentages neither platform's API gives us. */
function Headline({ data }: { data: PlayerStatsData }) {
  const log = data.season_log;
  if (!log) return null;
  const ppg = data.seasons.find((s) => s.season === log.season)?.ppg ?? null;
  const items = [
    { label: "Fan Pts", value: log.fantasy_points?.toFixed(2) },
    {
      label: "Pos Rank",
      value: log.position_rank !== null ? `${data.position_group} ${log.position_rank}` : null,
    },
    { label: "Pts / Game", value: ppg?.toFixed(2) },
  ].filter((item) => item.value !== null && item.value !== undefined);
  if (items.length === 0) return null;
  return (
    <dl className="pgl-headline" aria-label={`${log.season} season`}>
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

type Tab = PlayerCardTab;

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "gamelog", label: "Game Log" },
  { id: "stats", label: "Stats" },
];

function Tabs({ tab, onChange }: { tab: Tab; onChange: (tab: Tab) => void }) {
  return (
    <div className="pgl-tabs" role="tablist" aria-label="Player card">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`pstats-tab-${t.id}`}
          aria-selected={t.id === tab}
          aria-controls={`pstats-panel-${t.id}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export interface PlayerStatsPanelProps {
  player: Player;
  teamId: string | undefined;
  week: number;
  onClose: () => void;
}

export function PlayerStatsPanel({ player, teamId, week, onClose }: PlayerStatsPanelProps) {
  const { data, isLoading, isError } = usePlayerStats(player.id, teamId, week);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [tab, setTab] = useState<Tab>(rememberedPlayerCardTab);
  const chooseTab = (next: Tab) => {
    rememberPlayerCardTab(next);
    setTab(next);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Body scroll lock, as PlayerHealthPanel does — and focus moves into the dialog and
  // back to the name that opened it, so a keyboard user isn't left on the page behind.
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, []);

  const payload = data?.data;
  const bye = payload?.season_log?.bye_week ?? player.bye_week;

  return createPortal(
    <div
      className="draft-detail-overlay"
      onClick={onClose}
      data-testid="player-stats-overlay"
      role="presentation"
    >
      <div
        className="draft-detail-panel card pstats-panel"
        onClick={(event) => event.stopPropagation()}
        data-testid="player-stats-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${player.name} stats`}
      >
        <div className="draft-detail-header">
          <div className="pstats-identity">
            <Headshot player={player} />
            <div>
              <div className="pstats-name">{player.name}</div>
              <div className="player-meta">
                {player.position}
                {payload?.jersey_number ? ` #${payload.jersey_number}` : ""} ·{" "}
                {nflTeamName(player.nfl_team)}
                {bye ? ` · Bye ${bye}` : ""}
              </div>
              {payload && (
                <div className="player-meta">
                  {FORMAT_LABELS[payload.points_format]} scoring
                  {payload.points_format_fallback ? " (league is custom)" : ""}
                </div>
              )}
            </div>
          </div>
          <button ref={closeRef} type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>

        {isLoading && <p className="muted">Loading…</p>}
        {isError && (
          <p className="muted">Couldn&rsquo;t load stats. They&rsquo;ll retry on reopen.</p>
        )}

        {payload && (
          <>
            <Headline data={payload} />
            <Tabs tab={tab} onChange={chooseTab} />
            <div
              className="pgl-tabpanel"
              role="tabpanel"
              id={`pstats-panel-${tab}`}
              aria-labelledby={`pstats-tab-${tab}`}
            >
              {tab === "overview" && <ThisWeek data={payload} />}
              {tab === "gamelog" && (
                <SeasonGameLog data={payload} formatLabel={FORMAT_LABELS[payload.points_format]} />
              )}
              {tab === "stats" && (
                <>
                  {payload.game_log.length > 0 ? (
                    <>
                      <BoxScores data={payload} />
                      <Career data={payload} />
                    </>
                  ) : (
                    <p className="muted pstats-empty">
                      {payload.sleeper_id
                        ? "No games on record yet."
                        : "No stat history available for this player."}
                    </p>
                  )}
                  <p className="pstats-footnote">
                    Stats by Sportradar via Sleeper, regular season. FPTS in{" "}
                    {FORMAT_LABELS[payload.points_format]}.
                  </p>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
