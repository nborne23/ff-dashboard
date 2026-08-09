// Week-day rings cluster (topbar). Ported 1:1 from design/primitives.jsx.

import { ActivityRing, type ActivityRingTrack } from "./ActivityRing";

export interface DayRingsDay {
  letter: string;
  rings: ActivityRingTrack[];
}

export interface DayRingsProps {
  days: DayRingsDay[];
  today: number;
}

export function DayRings({ days, today }: DayRingsProps) {
  return (
    <div className="week-days">
      {days.map((d, i) => (
        <div key={i} className={"day-cell" + (i === today ? " today" : "")}>
          <span className="letter">{d.letter}</span>
          <ActivityRing size={20} stroke={2.5} gap={1} tracks={d.rings} />
        </div>
      ))}
    </div>
  );
}
