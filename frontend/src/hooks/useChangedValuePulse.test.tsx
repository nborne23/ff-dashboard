import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PULSE_ANIMATION_MS, useChangedValuePulse } from "./useChangedValuePulse";

describe("useChangedValuePulse", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("has no data-just-changed attribute on first render", () => {
    const { result } = renderHook(() => useChangedValuePulse(10));
    expect(result.current["data-just-changed"]).toBeUndefined();
  });

  it("sets data-just-changed when the value changes", () => {
    const { result, rerender } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 20 });

    expect(result.current["data-just-changed"]).toBe("true");
  });

  it("does not trigger when re-rendered with the same value", () => {
    const { result, rerender } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 10 });

    expect(result.current["data-just-changed"]).toBeUndefined();
  });

  it("clears data-just-changed after the animation timeout elapses", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 20 });
    expect(result.current["data-just-changed"]).toBe("true");

    act(() => {
      vi.advanceTimersByTime(PULSE_ANIMATION_MS);
    });

    expect(result.current["data-just-changed"]).toBeUndefined();
  });

  it("clears data-just-changed immediately when onAnimationEnd fires", () => {
    const { result, rerender } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 20 });
    expect(result.current["data-just-changed"]).toBe("true");

    act(() => {
      result.current.onAnimationEnd();
    });

    expect(result.current["data-just-changed"]).toBeUndefined();
  });

  it("re-triggers on a later change after having cleared", () => {
    const { result, rerender } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 20 });
    act(() => {
      result.current.onAnimationEnd();
    });
    rerender({ value: 30 });

    expect(result.current["data-just-changed"]).toBe("true");
  });

  it("does not error when unmounted mid-animation", () => {
    vi.useFakeTimers();
    const { result, rerender, unmount } = renderHook(({ value }) => useChangedValuePulse(value), {
      initialProps: { value: 10 },
    });

    rerender({ value: 20 });
    expect(result.current["data-just-changed"]).toBe("true");

    expect(() => unmount()).not.toThrow();
  });

  // Task 10.4: an SSE reconnect (or the visibility-change fallback in
  // api/events.ts) triggers `queryClient.invalidateQueries()`/refetch — for a query
  // whose upstream value hasn't actually moved, that refetch must not itself count as
  // a "change" just because a new response object came back over the wire.
  describe("SSE-reconnect-driven refetch", () => {
    function ScoreDisplay({ queryFn }: { queryFn: () => Promise<number> }) {
      const { data } = useQuery({ queryKey: ["score"], queryFn, initialData: 42 });
      const pulse = useChangedValuePulse(data);
      return (
        <span data-testid="score" {...pulse}>
          {data}
        </span>
      );
    }

    afterEach(() => cleanup());

    it("does not pulse when a reconnect-triggered refetch resolves to the same value", async () => {
      const queryClient = new QueryClient();
      const fetchScore = vi.fn().mockResolvedValue(42);

      render(
        <QueryClientProvider client={queryClient}>
          <ScoreDisplay queryFn={fetchScore} />
        </QueryClientProvider>,
      );
      expect(screen.getByTestId("score").getAttribute("data-just-changed")).toBeNull();

      // Simulates useLiveEvents' invalidateQueries() call on reconnect/visibility-change.
      await act(async () => {
        await queryClient.invalidateQueries({ queryKey: ["score"] });
      });
      await waitFor(() => expect(fetchScore).toHaveBeenCalled());

      expect(screen.getByTestId("score").getAttribute("data-just-changed")).toBeNull();
    });

    it("does pulse when a reconnect-triggered refetch resolves to a genuinely new value", async () => {
      const queryClient = new QueryClient();
      const fetchScore = vi.fn().mockResolvedValue(57);

      render(
        <QueryClientProvider client={queryClient}>
          <ScoreDisplay queryFn={fetchScore} />
        </QueryClientProvider>,
      );

      await act(async () => {
        await queryClient.invalidateQueries({ queryKey: ["score"] });
      });

      await waitFor(() => {
        expect(screen.getByTestId("score").getAttribute("data-just-changed")).toBe("true");
      });
    });
  });
});
