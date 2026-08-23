// Task 3.8 — the full draft board (drafted players stay visible, greyed + struck
// through, rather than being removed, so the user can see what went and to whom).
// Filter (position) and sort (ADP / tier / risk) are both client-side over the single
// already-loaded `useDraftBoard()` response — no server round trip per position tap or
// sort change. Rows are large tap targets (`.draft-row`, >=56px) since this is used
// one-handed on a phone during a live draft.

import { useMemo, useState } from "react";

import type { BoardPlayerOut } from "../../api/draft";
import { useDraftBoard } from "../../api/draft";
import { Skeleton } from "../../components/primitives";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { MarkDrafted } from "./MarkDrafted";
import { PlayerDetail } from "./PlayerDetail";

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "DST", "K"] as const;
type PositionFilter = (typeof POSITIONS)[number];

type SortKey = "adp" | "tier" | "risk";
const SORTS: { key: SortKey; label: string }[] = [
  { key: "adp", label: "ADP" },
  { key: "tier", label: "Tier" },
  { key: "risk", label: "Risk" },
];

/** Ascending, nulls sorted after every real value regardless of direction requested --
 * a missing ADP/tier isn't "best", it's "unknown", so it never jumps to the top. */
function compareNullable(a: number | null, b: number | null, direction: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (a - b) * direction;
}

function sortPlayers(players: BoardPlayerOut[], sortKey: SortKey): BoardPlayerOut[] {
  const sorted = [...players];
  if (sortKey === "adp") {
    sorted.sort((a, b) => compareNullable(a.adp_rank, b.adp_rank, 1));
  } else if (sortKey === "tier") {
    sorted.sort((a, b) => compareNullable(a.overall_tier, b.overall_tier, 1));
  } else {
    // Risk: highest risk_score first -- the whole point of sorting by risk is to spot
    // the risky players, so descending (nulls still pushed to the end).
    sorted.sort((a, b) => compareNullable(a.risk_score, b.risk_score, -1));
  }
  return sorted;
}

function PlayerMeta({ player }: { player: BoardPlayerOut }) {
  const bits: string[] = [];
  if (player.nfl_team) bits.push(player.nfl_team);
  if (player.bye) bits.push(`Bye ${player.bye}`);
  if (player.adp_rank) bits.push(`ADP ${player.adp_rank}`);
  if (player.overall_tier) bits.push(`Tier ${player.overall_tier}`);
  return <div className="player-meta">{bits.join(" · ") || "—"}</div>;
}

// `drafted_overall_pick` is briefly `null` during a mark-drafted mutation's optimistic
// window (the mutation never sends `overall_pick` -- the backend assigns it -- so the
// optimistic patch in api/draft.ts can't fabricate a real number yet). Omit the "#N"
// entirely rather than render a bare trailing "#" until the real value lands.
function PickNumber({ pick }: { pick: number | null }) {
  return pick === null ? null : <> · #{pick}</>;
}

function DraftedBadge({ player }: { player: BoardPlayerOut }) {
  if (player.is_my_pick) {
    return (
      <span className="pill win" style={{ flexShrink: 0 }}>
        You
        <PickNumber pick={player.drafted_overall_pick} />
      </span>
    );
  }
  return (
    <span className="pill bench" style={{ flexShrink: 0 }}>
      {player.drafted_by_team ?? "Drafted"}
      <PickNumber pick={player.drafted_overall_pick} />
    </span>
  );
}

// Task 6.3 -- tapping the name/meta area (not the Mine/Theirs action buttons) opens
// PlayerDetail. A plain <button> wraps just that region so it stays a single, obvious
// tap target without swallowing the MarkDrafted buttons' own clicks.
function BoardRow({ player, onSelect }: { player: BoardPlayerOut; onSelect: () => void }) {
  return (
    <div className={"draft-row" + (player.is_drafted ? " drafted" : "")} data-testid="board-row">
      <span className="pill pos">{player.position}</span>
      <button
        type="button"
        className="player-info"
        style={{
          background: "none",
          border: "none",
          textAlign: "left",
          padding: 0,
          font: "inherit",
          color: "inherit",
          cursor: "pointer",
        }}
        onClick={onSelect}
        aria-label={`View scouting detail for ${player.name}`}
      >
        <div className="player-name">
          {player.name}
          {player.out_for_season && (
            <span className="pill loss" style={{ marginLeft: 6 }}>
              OUT FOR SEASON
            </span>
          )}
          {player.rookie && (
            <span className="pill bench" style={{ marginLeft: 6 }}>
              R
            </span>
          )}
        </div>
        <PlayerMeta player={player} />
      </button>
      {player.is_drafted ? (
        <DraftedBadge player={player} />
      ) : (
        <div className="player-actions">
          <MarkDrafted player={player} />
        </div>
      )}
    </div>
  );
}

export function BoardList() {
  const boardQuery = useDraftBoard();
  const [position, setPosition] = useState<PositionFilter>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("adp");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<BoardPlayerOut | null>(null);

  const players = boardQuery.data?.data.players;

  const filteredAndSorted = useMemo(() => {
    const all = players ?? [];
    // Task 6.7 -- out-for-season players are excluded from the pool/recommendations
    // but stay on this board response specifically so they remain findable here; a
    // name search must never filter them out on that basis (only the position filter
    // and the search text apply -- there's no "hide out-for-season" toggle).
    const searched = search.trim()
      ? all.filter((p) => p.name.toLowerCase().includes(search.trim().toLowerCase()))
      : all;
    const filtered =
      position === "ALL" ? searched : searched.filter((p) => p.position === position);
    return sortPlayers(filtered, sortKey);
  }, [players, position, sortKey, search]);

  if (boardQuery.isError) {
    return (
      <ErrorCard
        error={boardQuery.error}
        fallbackMessage="Couldn't load the draft board."
        onRetry={() => void boardQuery.refetch()}
        testId="board-error"
      />
    );
  }

  if (boardQuery.isLoading || !boardQuery.data) {
    return (
      <div className="card" data-testid="board-skeleton" aria-hidden="true">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} width="100%" height={40} style={{ marginBottom: 8 }} />
        ))}
      </div>
    );
  }

  return (
    <div data-testid="board-list">
      <input
        type="search"
        placeholder="Search players by name…"
        aria-label="Search draft board by player name"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        style={{
          width: "100%",
          background: "var(--surface-2)",
          border: "none",
          borderRadius: 8,
          color: "var(--text)",
          fontSize: 14,
          fontFamily: "inherit",
          padding: "10px 12px",
          marginBottom: 10,
          outline: "none",
        }}
      />
      <div className="draft-filter-bar">
        <div className="segmented">
          {POSITIONS.map((pos) => (
            <button
              key={pos}
              type="button"
              className={pos === position ? "active" : ""}
              onClick={() => setPosition(pos)}
            >
              {pos}
            </button>
          ))}
        </div>
        <div className="segmented">
          {SORTS.map((s) => (
            <button
              key={s.key}
              type="button"
              className={s.key === sortKey ? "active" : ""}
              onClick={() => setSortKey(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card" style={{ padding: "0 12px" }}>
        {filteredAndSorted.length === 0 ? (
          <p className="muted" style={{ padding: 16 }}>
            No players match this filter.
          </p>
        ) : (
          filteredAndSorted.map((player) => (
            <BoardRow key={player.id} player={player} onSelect={() => setSelected(player)} />
          ))
        )}
      </div>
      <PlayerDetail player={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
