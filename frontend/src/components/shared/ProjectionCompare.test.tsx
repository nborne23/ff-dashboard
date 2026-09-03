import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DIVERGENCE_THRESHOLD, ProjectionCompare } from "./ProjectionCompare";

describe("ProjectionCompare", () => {
  afterEach(cleanup);

  it("renders an em dash when there is no second opinion", () => {
    // Unmatched player, job not yet run, or a custom-scoring league — all three mean
    // "we can't answer", which must not look like a projection of zero.
    const { container } = render(<ProjectionCompare own={14.2} ext={null} />);
    expect(container.textContent).toBe("—");
    expect(container.querySelector(".proj-ext-diverges")).toBeNull();
  });

  it("stays quiet when the two sources agree", () => {
    const { container } = render(<ProjectionCompare own={14.2} ext={14.9} />);
    expect(container.textContent).toBe("14.9");
    // Agreement is the common case; colouring it would drown the rows that matter.
    expect(container.querySelector(".proj-ext-diverges")).toBeNull();
  });

  it("colours a materially higher independent projection", () => {
    render(<ProjectionCompare own={14.2} ext={14.2 + DIVERGENCE_THRESHOLD} />);
    const el = screen.getByText("15.7");
    expect(el.className).toContain("proj-ext-diverges");
    expect(el.className).toContain("pos");
    expect(el.getAttribute("title")).toContain("higher by 1.5");
  });

  it("colours a materially lower one the other way", () => {
    render(<ProjectionCompare own={20.0} ext={16.0} />);
    const el = screen.getByText("16.0");
    expect(el.className).toContain("neg");
    expect(el.getAttribute("title")).toContain("lower by 4.0");
  });

  it("treats a projection of zero as a real number, not a missing one", () => {
    // 0.0 means "projected to score nothing" (a benched or injured starter); null means
    // "no projection". Rendering them alike would be the same defect the waiver screen's
    // formatPoints already guards against.
    const { container } = render(<ProjectionCompare own={9.0} ext={0} />);
    expect(container.textContent).toBe("0.0");
  });
});
