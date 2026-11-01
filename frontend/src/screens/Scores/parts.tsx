// Small pieces shared by the Scores list and the game detail.

import { useEffect, useRef, useState } from "react";

import type { ScoreTeam } from "../../api/scores";

/** An NFL team's logo, falling back to its abbreviation in a disc when the image fails. */
export function TeamMark({ team, size = 28 }: { team: ScoreTeam; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (!team.logo || failed) {
    return (
      <span
        className="sc-team-mark sc-team-mark-fallback"
        style={{ width: size, height: size, fontSize: size * 0.34 }}
        aria-hidden="true"
      >
        {team.abbr}
      </span>
    );
  }
  return (
    <img
      className="sc-team-mark"
      src={team.logo}
      alt=""
      width={size}
      height={size}
      onError={() => setFailed(true)}
    />
  );
}

export interface WeekStripProps {
  weeks: number[];
  selected: number;
  current: number | null;
  onSelect: (week: number) => void;
}

/** Sleeper's horizontal week scroller: "CURRENT" over this week, a dot under the chosen one. */
export function WeekStrip({ weeks, selected, current, onSelect }: WeekStripProps) {
  const selectedRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    // `scrollIntoView` is missing under jsdom; the strip still works without it.
    selectedRef.current?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [selected]);

  return (
    <div className="sc-weeks" role="tablist" aria-label="NFL week">
      {weeks.map((week) => {
        const isSelected = week === selected;
        return (
          <button
            key={week}
            ref={isSelected ? selectedRef : undefined}
            type="button"
            role="tab"
            aria-selected={isSelected}
            className={"sc-week" + (isSelected ? " selected" : "")}
            onClick={() => onSelect(week)}
          >
            <span className="sc-week-current">{week === current ? "Current" : " "}</span>
            <span className="sc-week-label">week {week}</span>
          </button>
        );
      })}
    </div>
  );
}
