// Task 10.5: verifies the TweaksPanel's sidebar-width and aurora-intensity sliders
// actually flow through the ui store into rendered CSS output (App.tsx's effect that
// sets `--sidebar-w`, and the `auroraColorForPath`-derived `--aurora-color`). Both were
// already wired on inspection; this locks that in with an assertion instead of relying
// on eyeballing the prototype.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";
import { COLLAPSED_SIDEBAR_W, TWEAK_DEFAULTS, useUiStore } from "./stores/ui";

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App tweaks live-wiring (task 10.5)", () => {
  afterEach(() => {
    cleanup();
    useUiStore.setState({ tweaks: TWEAK_DEFAULTS });
  });

  it("reflects the sidebarWidth tweak in the --sidebar-w CSS custom property", () => {
    renderApp();
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${TWEAK_DEFAULTS.sidebarWidth}px`,
    );

    act(() => {
      useUiStore.setState({ tweaks: { ...TWEAK_DEFAULTS, sidebarWidth: 264 } });
    });

    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe("264px");
  });

  it("reflects the rowHeight and sparkThickness tweaks in their CSS custom properties", () => {
    renderApp();

    act(() => {
      useUiStore.setState({ tweaks: { ...TWEAK_DEFAULTS, rowHeight: 64, sparkThickness: 2.5 } });
    });

    expect(document.documentElement.style.getPropertyValue("--row-h")).toBe("64px");
    expect(document.documentElement.style.getPropertyValue("--spark-thick")).toBe("2.5px");
  });

  it("modulates the Aurora gradient's alpha from the auroraIntensity tweak", () => {
    const { container } = renderApp();
    const aurora = () => container.querySelector(".aurora") as HTMLElement;

    expect(aurora().style.getPropertyValue("--aurora-color")).toBe(
      `rgba(255, 45, 85, ${TWEAK_DEFAULTS.auroraIntensity})`,
    );

    act(() => {
      useUiStore.setState({ tweaks: { ...TWEAK_DEFAULTS, auroraIntensity: 0.35 } });
    });

    expect(aurora().style.getPropertyValue("--aurora-color")).toBe("rgba(255, 45, 85, 0.35)");
  });
});

describe("sidebar collapse", () => {
  afterEach(() => {
    cleanup();
    useUiStore.setState({ tweaks: TWEAK_DEFAULTS, sidebarCollapsed: false });
  });

  function appEl(container: HTMLElement): HTMLElement {
    return container.querySelector(".app") as HTMLElement;
  }

  it("starts expanded, with no data-sidebar attribute", () => {
    const { container } = renderApp();

    expect(appEl(container).getAttribute("data-sidebar")).toBeNull();
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${TWEAK_DEFAULTS.sidebarWidth}px`,
    );
  });

  it("collapses to the icon-only width and back from the toggle", () => {
    const { container } = renderApp();

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(appEl(container).getAttribute("data-sidebar")).toBe("collapsed");
    // The grid column narrows to exactly the width the <1024px responsive rule uses, so
    // the manual and automatic collapses share one geometry.
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${COLLAPSED_SIDEBAR_W}px`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));

    expect(appEl(container).getAttribute("data-sidebar")).toBeNull();
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${TWEAK_DEFAULTS.sidebarWidth}px`,
    );
  });

  it("collapsing overrides the sidebarWidth tweak rather than fighting it", () => {
    renderApp();

    act(() => {
      useUiStore.setState({ tweaks: { ...TWEAK_DEFAULTS, sidebarWidth: 300 } });
    });
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe("300px");

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${COLLAPSED_SIDEBAR_W}px`,
    );

    // Expanding restores the tweak's width, not the default.
    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe("300px");
  });

  it("keeps the toggle reachable while collapsed, and reports state to assistive tech", () => {
    renderApp();

    const toggle = () => screen.getByRole("button", { name: /sidebar$/ });
    expect(toggle().getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(toggle());

    // Still in the DOM and still operable — a collapse the user cannot undo from the
    // collapsed state would be a one-way door.
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
    expect(toggle().getAttribute("aria-label")).toBe("Expand sidebar");
  });

  it("restores a persisted collapsed state on mount", () => {
    // The wall display is restarted by a LaunchAgent; a collapse that reset every time
    // would have to be redone on every restart.
    useUiStore.setState({ sidebarCollapsed: true });
    const { container } = renderApp();

    expect(appEl(container).getAttribute("data-sidebar")).toBe("collapsed");
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe(
      `${COLLAPSED_SIDEBAR_W}px`,
    );
  });
});
