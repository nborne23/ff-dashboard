import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useFreshness } from "./useFreshness";

const NOW = new Date("2025-12-07T18:00:00.000Z");

function asOfSecondsAgo(seconds: number): string {
  return new Date(NOW.getTime() - seconds * 1000).toISOString();
}

describe("useFreshness", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows a seconds-ago label for a recent as_of", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(asOfSecondsAgo(12)));

    expect(result.current.label).toBe("Last updated 12s ago");
    expect(result.current.stale).toBe(false);
  });

  it("switches to a minutes-ago label past 60 seconds", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(asOfSecondsAgo(3 * 60)));

    expect(result.current.label).toBe("Last updated 3m ago");
  });

  it("is stale once 90 seconds have elapsed", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(asOfSecondsAgo(91)));

    expect(result.current.stale).toBe(true);
  });

  it("is not stale just under the 90-second threshold", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(asOfSecondsAgo(89)));

    expect(result.current.stale).toBe(false);
  });

  it("ticks every second as time passes", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(NOW.toISOString()));
    expect(result.current.label).toBe("Last updated 0s ago");

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.label).toBe("Last updated 5s ago");
  });

  it("crosses into staleness while mounted, without remounting", () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);

    const { result } = renderHook(() => useFreshness(NOW.toISOString()));
    expect(result.current.stale).toBe(false);

    act(() => {
      vi.advanceTimersByTime(91_000);
    });

    expect(result.current.stale).toBe(true);
  });

  it("falls back gracefully when as_of is null or undefined", () => {
    const nullResult = renderHook(() => useFreshness(null));
    expect(nullResult.result.current.stale).toBe(false);

    const undefinedResult = renderHook(() => useFreshness(undefined));
    expect(undefinedResult.result.current.stale).toBe(false);
  });
});
