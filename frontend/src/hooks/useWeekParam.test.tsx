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
    useUiStore.setState({ week: 1 });
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
    useUiStore.setState({ week: 1 });
    renderProbe("/?week=1");

    await waitFor(() => {
      expect(screen.getByTestId("url-week").textContent).toBe("1");
    });
    expect(screen.getByTestId("store-week").textContent).toBe("1");
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
