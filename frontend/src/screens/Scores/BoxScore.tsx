// A team's tab on the game detail: a plain box score built from the same stat lines the
// Fantasy tab shows, so the two can never disagree.

import type { FantasyPlayer, GameDetail } from "../../api/scores";

interface Column {
  label: string;
  value: (stats: Record<string, number>) => string;
}

const n = (key: string) => (stats: Record<string, number>) => String(stats[key] ?? 0);
const ratio = (made: string, att: string) => (stats: Record<string, number>) =>
  `${stats[made] ?? 0}/${stats[att] ?? 0}`;

interface Section {
  title: string;
  include: (player: FantasyPlayer) => boolean;
  sortKey: string;
  columns: Column[];
}

const SECTIONS: Section[] = [
  {
    title: "Passing",
    include: (p) => Boolean(p.stats.pass_att),
    sortKey: "pass_yd",
    columns: [
      { label: "C/ATT", value: ratio("pass_cmp", "pass_att") },
      { label: "YDS", value: n("pass_yd") },
      { label: "TD", value: n("pass_td") },
      { label: "INT", value: n("pass_int") },
    ],
  },
  {
    title: "Rushing",
    include: (p) => Boolean(p.stats.rush_att),
    sortKey: "rush_yd",
    columns: [
      { label: "CAR", value: n("rush_att") },
      { label: "YDS", value: n("rush_yd") },
      { label: "TD", value: n("rush_td") },
      { label: "LNG", value: n("rush_lng") },
    ],
  },
  {
    title: "Receiving",
    include: (p) => Boolean(p.stats.rec || p.stats.rec_tgt),
    sortKey: "rec_yd",
    columns: [
      { label: "REC", value: n("rec") },
      { label: "TGT", value: n("rec_tgt") },
      { label: "YDS", value: n("rec_yd") },
      { label: "TD", value: n("rec_td") },
    ],
  },
  {
    title: "Kicking",
    include: (p) => p.position === "K" && Boolean(p.stats.fga || p.stats.xpa),
    sortKey: "fgm",
    columns: [
      { label: "FG", value: ratio("fgm", "fga") },
      { label: "XP", value: ratio("xpm", "xpa") },
      { label: "LNG", value: n("fgm_lng") },
    ],
  },
  {
    title: "Defense",
    include: (p) => p.position === "DEF" && Object.keys(p.stats).length > 0,
    sortKey: "sack",
    columns: [
      { label: "SACK", value: n("sack") },
      { label: "INT", value: n("int") },
      { label: "FR", value: n("fum_rec") },
      { label: "TD", value: n("td") },
      { label: "PA", value: n("pts_allow") },
    ],
  },
];

export function BoxScore({ detail, side }: { detail: GameDetail; side: "away" | "home" }) {
  const players = detail.groups.flatMap((group) => group[side]);
  const sections = SECTIONS.map((section) => ({
    section,
    rows: players
      .filter(section.include)
      .sort((a, b) => (b.stats[section.sortKey] ?? 0) - (a.stats[section.sortKey] ?? 0)),
  })).filter(({ rows }) => rows.length > 0);

  if (sections.length === 0) {
    return (
      <div className="sc-empty-inline" data-testid="box-empty">
        No stats yet for {detail.game[side].name}.
      </div>
    );
  }

  return (
    <div className="sc-box" data-testid={`box-${side}`}>
      {sections.map(({ section, rows }) => (
        <table key={section.title} className="sc-box-table">
          <thead>
            <tr>
              <th scope="col">{section.title}</th>
              {section.columns.map((column) => (
                <th key={column.label} scope="col" className="num">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((player) => (
              <tr key={player.sleeper_id}>
                <th scope="row">{player.short_name}</th>
                {section.columns.map((column) => (
                  <td key={column.label} className="num">
                    {column.value(player.stats)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}
