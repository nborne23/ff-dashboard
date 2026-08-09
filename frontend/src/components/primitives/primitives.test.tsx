import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityRing } from "./ActivityRing";
import { BarChart } from "./BarChart";
import { DayRings } from "./DayRings";
import { HorizBar } from "./HorizBar";
import {
  IconArrowL,
  IconArrowR,
  IconBolt,
  IconCalendar,
  IconCheck,
  IconChevR,
  IconDashboard,
  IconFlame,
  IconFootball,
  IconLock,
  IconMatchups,
  IconPlus,
  IconRefresh,
  IconSeason,
  IconSettings,
  IconShield,
  IconStar,
  IconTeams,
  IconUp,
  IconX,
} from "./Icons";
import { MiniRing } from "./MiniRing";
import { Sparkline } from "./Sparkline";

describe("primitives", () => {
  it("ActivityRing renders with a track set matching the design snapshot", () => {
    const { container } = render(
      <ActivityRing
        size={88}
        stroke={9}
        tracks={[
          { value: 0.7, color: "#FF2D55" },
          { value: 0.5, color: "#30D158" },
        ]}
        label="87.4"
        sublabel="pts"
      />,
    );
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("MiniRing renders", () => {
    const { container } = render(
      <MiniRing size={30} stroke={4} value={0.6} color="#FF2D55" icon="arrow" />,
    );
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("Sparkline renders", () => {
    const { container } = render(
      <Sparkline data={[78, 92, 64, 88, 94, 87]} width={140} height={48} />,
    );
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("BarChart renders", () => {
    const data = [
      { x: "0:00", y: 5 },
      { x: "", y: 12 },
      { x: "", y: 20 },
      { x: "4:00", y: 8 },
    ];
    const { container } = render(<BarChart data={data} refLineY={15} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("HorizBar renders", () => {
    const { container } = render(<HorizBar value={18} max={24} refValue={14} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("DayRings renders", () => {
    const days = [
      { letter: "T", rings: [{ value: 0.7, color: "#FF2D55" }] },
      { letter: "F", rings: [{ value: 0.4, color: "#FF2D55" }] },
    ];
    const { container } = render(<DayRings days={days} today={1} />);
    expect(container.innerHTML).toMatchSnapshot();
  });

  it("Icons render (all Icon* components)", () => {
    const { container } = render(
      <>
        <IconDashboard />
        <IconTeams />
        <IconMatchups />
        <IconSeason />
        <IconSettings />
        <IconChevR />
        <IconArrowL />
        <IconArrowR />
        <IconRefresh />
        <IconUp />
        <IconFootball />
        <IconCalendar />
        <IconShield />
        <IconBolt />
        <IconStar />
        <IconFlame />
        <IconCheck />
        <IconX />
        <IconPlus />
        <IconLock />
      </>,
    );
    expect(container.innerHTML).toMatchSnapshot();
  });
});
