import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LEAD_FLIP_ANIMATION_MS, useLeadFlip } from "./useLeadFlip";

function Probe({ margin }: { margin: number }) {
  const props = useLeadFlip(margin);
  return <div data-testid="panel" {...props} />;
}

function flipped(container: HTMLElement): boolean {
  return (
    container.querySelector("[data-testid='panel']")?.getAttribute("data-lead-flip") === "true"
  );
}

describe("useLeadFlip", () => {
  afterEach(cleanup);

  it("does not fire on first render, however large the margin", () => {
    const { container } = render(<Probe margin={42} />);
    expect(flipped(container)).toBe(false);
  });

  it("does not fire on first render with a negative margin either", () => {
    const { container } = render(<Probe margin={-42} />);
    expect(flipped(container)).toBe(false);
  });

  it("fires when the margin crosses from leading to trailing", () => {
    const { container, rerender } = render(<Probe margin={8.4} />);
    act(() => rerender(<Probe margin={-2.1} />));
    expect(flipped(container)).toBe(true);
  });

  it("fires when the margin crosses from trailing to leading", () => {
    const { container, rerender } = render(<Probe margin={-8.4} />);
    act(() => rerender(<Probe margin={3.3} />));
    expect(flipped(container)).toBe(true);
  });

  it("does NOT fire when only the magnitude changes", () => {
    const { container, rerender } = render(<Probe margin={3} />);
    act(() => rerender(<Probe margin={18} />));
    expect(flipped(container)).toBe(false);

    act(() => rerender(<Probe margin={0.9} />));
    expect(flipped(container)).toBe(false);
  });

  it("does not fire on a magnitude change while trailing", () => {
    const { container, rerender } = render(<Probe margin={-3} />);
    act(() => rerender(<Probe margin={-25} />));
    expect(flipped(container)).toBe(false);
  });

  it("does not fire on entering the tie band", () => {
    const { container, rerender } = render(<Probe margin={5} />);
    act(() => rerender(<Probe margin={0} />));
    expect(flipped(container)).toBe(false);
  });

  it("fires exactly once for a flip that passes through a tie", () => {
    // The reason the comparator is `previous * next < 0` rather than
    // `sign(previous) !== sign(next)`: the inequality form would fire on entering the
    // tie AND again on leaving it, double-pulsing one lead change.
    const { container, rerender } = render(<Probe margin={5} />);

    act(() => rerender(<Probe margin={0} />));
    expect(flipped(container)).toBe(false);

    act(() => rerender(<Probe margin={-5} />));
    expect(flipped(container)).toBe(true);
  });

  it("clears itself after the animation duration", () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<Probe margin={4} />);
      act(() => rerender(<Probe margin={-4} />));
      expect(flipped(container)).toBe(true);

      act(() => vi.advanceTimersByTime(LEAD_FLIP_ANIMATION_MS + 10));
      expect(flipped(container)).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
