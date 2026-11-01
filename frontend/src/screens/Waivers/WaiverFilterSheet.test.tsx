import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_WAIVER_FILTERS, sheetFiltersOf, type SheetFilters } from "./filters";
import { WaiverFilterSheet } from "./WaiverFilterSheet";

const defaults = sheetFiltersOf(DEFAULT_WAIVER_FILTERS);
const GAME_DAYS = ["2026-11-05", "2026-11-08", "2026-11-09"];

function renderSheet(filters: SheetFilters = defaults, gameDays: string[] = GAME_DAYS) {
  const onApply = vi.fn();
  const onClose = vi.fn();
  render(
    <WaiverFilterSheet filters={filters} gameDays={gameDays} onApply={onApply} onClose={onClose} />,
  );
  return { onApply, onClose };
}

function statusGroup() {
  return screen.getByRole("radiogroup", { name: "Status" });
}

describe("WaiverFilterSheet", () => {
  afterEach(cleanup);

  it("renders Yahoo's sheet: title, Show My Team, status list and the two actions", () => {
    renderSheet();

    expect(screen.getByRole("dialog", { name: "Filters" })).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Show My Team" })).toBeTruthy();
    const options = within(statusGroup()).getAllByRole("radio");
    expect(options.map((o) => o.textContent)).toEqual([
      "All Available",
      "All Available (Games Thursday - 11/5)",
      "All Available (Games Sunday - 11/8)",
      "All Available (Games Monday - 11/9)",
      "Free Agents Only",
      "Waivers Only",
      "All Players",
    ]);
    expect(options[0].getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("button", { name: "Reset" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply Filters" })).toBeTruthy();
  });

  it("applies the drafted choices only when Apply Filters is pressed", () => {
    const { onApply } = renderSheet();

    fireEvent.click(within(statusGroup()).getByRole("radio", { name: "Waivers Only" }));
    fireEvent.click(screen.getByRole("switch", { name: "Show My Team" }));
    fireEvent.click(screen.getByRole("radio", { name: /% Rostered/ }));
    expect(onApply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));

    expect(onApply).toHaveBeenCalledWith({
      status: "waivers",
      gameDay: null,
      showMine: true,
      sort: "owned",
    });
  });

  it("picks a game day as an 'All Available' status", () => {
    const { onApply } = renderSheet({ ...defaults, status: "waivers" });

    fireEvent.click(
      within(statusGroup()).getByRole("radio", { name: "All Available (Games Sunday - 11/8)" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));

    expect(onApply).toHaveBeenCalledWith({
      ...defaults,
      status: "available",
      gameDay: "2026-11-08",
    });
  });

  it("resets the draft to the defaults without applying it", () => {
    const { onApply } = renderSheet({
      status: "all",
      gameDay: null,
      showMine: true,
      sort: "owned",
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    expect(onApply).not.toHaveBeenCalled();
    expect(
      within(statusGroup())
        .getByRole("radio", { name: "All Available" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect(screen.getByRole("switch", { name: "Show My Team" }).getAttribute("aria-checked")).toBe(
      "false",
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));
    expect(onApply).toHaveBeenCalledWith(defaults);
  });

  it("shows a remembered game day that has played out as plain 'All Available'", () => {
    renderSheet({ ...defaults, gameDay: "2026-11-05" }, ["2026-11-08"]);

    const checked = within(statusGroup())
      .getAllByRole("radio")
      .filter((o) => o.getAttribute("aria-checked") === "true");
    expect(checked.map((o) => o.textContent)).toEqual(["All Available"]);
  });

  it("closes from the X, from Escape, and from a tap outside — never from a tap inside", () => {
    const { onClose } = renderSheet();

    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close filters" }));
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("waiver-filter-overlay"));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("locks the page scroll while open and restores it on close", () => {
    document.body.style.overflow = "auto";
    const { unmount } = render(
      <WaiverFilterSheet filters={defaults} gameDays={[]} onApply={vi.fn()} onClose={vi.fn()} />,
    );

    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("auto");
  });
});
