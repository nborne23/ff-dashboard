// Sample data for GridIron prototype.

const TEAMS = [
  {
    id: "yhb",
    name: "Highland Bombers",
    league: "Highland Bros Dynasty",
    platform: "yahoo",
    rank: "2nd / 12",
    record: "8–3",
    score: 87.4,
    oppScore: 71.2,
    opponent: "The Touchdown Club",
    spark: [78, 92, 64, 88, 94, 87],
    live: true,
    accent: "#FF2D55",
  },
  {
    id: "ele",
    name: "Eleven Thunder",
    league: "Office League",
    platform: "espn",
    rank: "1st / 10",
    record: "9–2",
    score: 102.7,
    oppScore: 89.1,
    opponent: "Beard Mode",
    spark: [88, 75, 96, 102, 110, 102],
    live: true,
    accent: "#FF2D55",
  },
  {
    id: "ach",
    name: "Achilles Heels",
    league: "Friday Night Lights",
    platform: "espn",
    rank: "5th / 14",
    record: "6–5",
    score: 64.9,
    oppScore: 78.4,
    opponent: "Gronk Stars",
    spark: [70, 88, 65, 72, 60, 64],
    live: false,
    accent: "#FF2D55",
  },
  {
    id: "byd",
    name: "Bayside Tigers",
    league: "Old Friends Keeper",
    platform: "yahoo",
    rank: "3rd / 12",
    record: "7–4",
    score: 91.3,
    oppScore: 88.0,
    opponent: "Saved By the Belichick",
    spark: [85, 79, 92, 87, 95, 91],
    live: true,
    accent: "#FF2D55",
  },
  {
    id: "rvr",
    name: "River Phantoms",
    league: "Family League",
    platform: "yahoo",
    rank: "4th / 8",
    record: "5–6",
    score: 73.5,
    oppScore: 69.2,
    opponent: "Mom's Spaghetti",
    spark: [60, 72, 68, 74, 80, 73],
    live: false,
    accent: "#FF2D55",
  },
  {
    id: "stl",
    name: "Stallion 6",
    league: "Money League",
    platform: "espn",
    rank: "6th / 10",
    record: "5–6",
    score: 68.0,
    oppScore: 84.1,
    opponent: "Dak To Reality",
    spark: [82, 70, 64, 78, 72, 68],
    live: false,
    accent: "#FF2D55",
  },
];

const ROSTER = [
  { slot: "QB",  name: "Patrick Mahomes",   pos: "QB",  team: "KC",  opp: "vs DEN", status: "LIVE Q3 7:42",   proj: 22.4, actual: 19.8, live: true },
  { slot: "RB1", name: "Bijan Robinson",    pos: "RB",  team: "ATL", opp: "@ NO",   status: "FINAL",          proj: 18.6, actual: 24.1, live: false },
  { slot: "RB2", name: "James Cook",        pos: "RB",  team: "BUF", opp: "vs NYJ", status: "LIVE Q2 0:48",   proj: 13.2, actual: 11.4, live: true },
  { slot: "WR1", name: "Justin Jefferson",  pos: "WR",  team: "MIN", opp: "@ DET",  status: "Mon 8:15",       proj: 19.4, actual: 0,    live: false },
  { slot: "WR2", name: "DeVonta Smith",     pos: "WR",  team: "PHI", opp: "vs DAL", status: "FINAL",          proj: 14.0, actual: 16.7, live: false },
  { slot: "TE",  name: "Sam LaPorta",       pos: "TE",  team: "DET", opp: "vs MIN", status: "Mon 8:15",       proj: 10.8, actual: 0,    live: false },
  { slot: "FLEX",name: "Rachaad White",     pos: "RB",  team: "TB",  opp: "@ CAR",  status: "FINAL",          proj: 11.5, actual: 8.2,  live: false },
  { slot: "K",   name: "Justin Tucker",     pos: "K",   team: "BAL", opp: "vs CIN", status: "FINAL",          proj: 8.4,  actual: 11.0, live: false },
  { slot: "DST", name: "Cowboys D/ST",      pos: "DST", team: "DAL", opp: "@ PHI",  status: "FINAL",          proj: 7.0,  actual: 4.0,  live: false },
];

const BENCH = [
  { slot: "BN", name: "Russell Wilson",     pos: "QB", team: "PIT", opp: "vs CLE", status: "FINAL", proj: 15.2, actual: 12.8 },
  { slot: "BN", name: "Tyjae Spears",       pos: "RB", team: "TEN", opp: "@ JAX",  status: "FINAL", proj: 7.8,  actual: 11.2 },
  { slot: "BN", name: "Calvin Ridley",      pos: "WR", team: "TEN", opp: "@ JAX",  status: "FINAL", proj: 11.0, actual: 6.4 },
  { slot: "BN", name: "Tank Dell",          pos: "WR", team: "HOU", opp: "vs JAX", status: "Sun 1:00", proj: 12.1, actual: 0 },
  { slot: "IR", name: "Aaron Jones",        pos: "RB", team: "MIN", opp: "—",      status: "OUT",   proj: 0,    actual: 0 },
];

const H2H = [
  { pos: "QB",   me: { name: "P. Mahomes",  pts: 19.8 }, opp: { name: "J. Allen",    pts: 23.4 } },
  { pos: "RB1",  me: { name: "B. Robinson", pts: 24.1 }, opp: { name: "S. Barkley",  pts: 18.2 } },
  { pos: "RB2",  me: { name: "J. Cook",     pts: 11.4 }, opp: { name: "K. Walker",   pts: 14.0 } },
  { pos: "WR1",  me: { name: "J. Jefferson",pts: 0.0  }, opp: { name: "C. Lamb",     pts: 22.7 } },
  { pos: "WR2",  me: { name: "D. Smith",    pts: 16.7 }, opp: { name: "A. St. Brown",pts: 12.5 } },
  { pos: "TE",   me: { name: "S. LaPorta",  pts: 0.0  }, opp: { name: "T. Kelce",    pts: 9.4  } },
  { pos: "FLEX", me: { name: "R. White",    pts: 8.2  }, opp: { name: "D. Adams",    pts: 13.1 } },
  { pos: "K",    me: { name: "J. Tucker",   pts: 11.0 }, opp: { name: "H. Butker",   pts: 7.0  } },
  { pos: "DST",  me: { name: "Cowboys",     pts: 4.0  }, opp: { name: "Ravens",      pts: 12.0 } },
];

const SEASON = [
  { wk:1, score: 102.4, opp: 88.1, w: true,  oppName: "Beard Mode" },
  { wk:2, score: 78.0,  opp: 95.4, w: false, oppName: "Gronk Stars" },
  { wk:3, score: 124.6, opp: 91.0, w: true,  oppName: "Mom's Spaghetti" },
  { wk:4, score: 88.2,  opp: 86.1, w: true,  oppName: "Saved By the Belichick" },
  { wk:5, score: 71.5,  opp: 84.0, w: false, oppName: "Touchdown Club" },
  { wk:6, score: 96.8,  opp: 80.2, w: true,  oppName: "Dak To Reality" },
  { wk:7, score: 110.2, opp: 92.5, w: true,  oppName: "Stallion 6" },
  { wk:8, score: 64.0,  opp: 87.7, w: false, oppName: "Eleven Thunder" },
  { wk:9, score: 105.9, opp: 79.3, w: true,  oppName: "Beard Mode" },
  { wk:10,score: 92.1,  opp: 75.0, w: true,  oppName: "Mom's Spaghetti" },
  { wk:11,score: 117.4, opp: 99.8, w: true,  oppName: "Touchdown Club" },
  { wk:12,score: 81.2,  opp: 88.4, w: false, oppName: "Gronk Stars" },
  { wk:13,score: 99.5,  opp: 76.2, w: true,  oppName: "Stallion 6" },
  { wk:14,score: 87.4,  opp: 71.2, w: true,  oppName: "Touchdown Club", current: true },
];

// Move-style intra-game scoring chart (24 hour minute-buckets)
const MOVE_CHART_DATA = (() => {
  const arr = [];
  for (let i = 0; i < 96; i++) {
    let v = 0;
    // Sunday game windows (10am, 1pm, 4pm, 8pm)
    if (i > 40 && i < 56) v = Math.random() * 20 + 5;
    else if (i > 60 && i < 78) v = Math.random() * 28 + 8;
    else if (i > 78 && i < 86) v = Math.random() * 16 + 4;
    arr.push({ x: i % 24 === 0 ? `${i/4}:00` : "", y: v });
  }
  return arr;
})();

const LIVE_GAMES = [
  { home: "KC",  away: "DEN", hScore: 21, aScore: 14, q: "Q3 7:42",  mine: 2 },
  { home: "BUF", away: "NYJ", hScore: 17, aScore: 10, q: "Q2 0:48",  mine: 1 },
  { home: "PHI", away: "DAL", hScore: 28, aScore: 21, q: "FINAL",    mine: 2 },
  { home: "BAL", away: "CIN", hScore: 31, aScore: 24, q: "FINAL",    mine: 1 },
  { home: "TB",  away: "CAR", hScore: 24, aScore: 17, q: "FINAL",    mine: 1 },
  { home: "MIN", away: "DET", hScore: 0,  aScore: 0,  q: "Mon 8:15", mine: 2 },
];

// Day-of-week rings (top bar)
const WEEK_DAYS = [
  { letter: "T", rings: [{ value: 0.7, color: "#FF2D55" }, { value: 0.5, color: "#30D158" }, { value: 0.6, color: "#64D2FF" }] },
  { letter: "F", rings: [{ value: 0.4, color: "#FF2D55" }, { value: 0.3, color: "#30D158" }, { value: 0.2, color: "#64D2FF" }] },
  { letter: "S", rings: [{ value: 0.0, color: "#FF2D55" }, { value: 0.0, color: "#30D158" }, { value: 0.0, color: "#64D2FF" }] },
  { letter: "S", rings: [{ value: 0.85,color: "#FF2D55" }, { value: 0.7, color: "#30D158" }, { value: 0.65,color: "#64D2FF" }] },
  { letter: "M", rings: [{ value: 0.0, color: "#FF2D55" }, { value: 0.0, color: "#30D158" }, { value: 0.0, color: "#64D2FF" }] },
];

Object.assign(window, {
  TEAMS, ROSTER, BENCH, H2H, SEASON, MOVE_CHART_DATA, LIVE_GAMES, WEEK_DAYS,
});
