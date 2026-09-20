import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useUiStore } from "../stores/ui";
import { useWeekParam } from "./useWeekParam";

function Probe() {
  useWeekParam();
  const week = useUiStore((s) => s.week);
  const [searchParams] = useSearchParams();
  return (
    <div>
      <span data-testid="store-week">{week}</span>
      <span data-testid="url-week">{searchParams.get("week") ?? ""}</span>
    </div>
  );
}

function renderProbe(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Probe />
    </MemoryRouter>,
  );
}

describe("useWeekParam", () => {
  afterEach(() => {
    cleanup();
    useUiStore.setState({ week: 1, weekPinned: false });
  });

  it("initializes the store from ?week= present in the URL on load", async () => {
    renderProbe("/?week=14");

    await waitFor(() => {
      expect(screen.getByTestId("store-week").textContent).toBe("14");
    });
    expect(screen.getByTestId("url-week").textContent).toBe("14");
  });

  it("writes the store's current week into the URL when none is present", async () => {
    renderProbe("/");

    await waitFor(() => {
      expect(screen.getByTestId("url-week").textContent).toBe("1");
    });
    expect(useUiStore.getState().week).toBe(1);
  });

  it("leaves the store alone when the URL already matches it", async () => {
    useUiStore.setState({ week: 1, weekPinned: false });
    renderProbe("/?week=1");

    await waitFor(() => {
      expect(screen.getByTestId("url-week").textContent).toBe("1");
    });
    expect(screen.getByTestId("store-week").textContent).toBe("1");
  });

  it("pins a ?week= that already matches the store, so the default never overrides it", async () => {
    // `?week=1` names week 1 as explicitly as `?week=14` names 14. Skipping `setWeek`
    // because the value happens to match would leave the week unpinned, and
    // `useCurrentWeekDefault` would then replace the user's choice with the live week.
    useUiStore.setState({ week: 1, weekPinned: false });
    renderProbe("/?week=1");

    await waitFor(() => {
      expect(useUiStore.getState().weekPinned).toBe(true);
    });
  });

  it("reflects subsequent store changes (Topbar back/forward) into the URL", async () => {
    renderProbe("/?week=5");
    await waitFor(() => {
      expect(screen.getByTestId("store-week").textContent).toBe("5");
    });

    act(() => {
      useUiStore.getState().setWeek(6);
    });

    await waitFor(() => {
      expect(screen.getByTestId("url-week").textContent).toBe("6");
    });
    expect(screen.getByTestId("store-week").textContent).toBe("6");
  });

  it("ignores a non-numeric ?week= value and keeps the store default", async () => {
    renderProbe("/?week=bogus");

    await waitFor(() => {
      expect(screen.getByTestId("store-week").textContent).toBe("1");
    });
  });
});
