// The shell: sidebar collapse, the phone tab bar, and the absence of the retired
// developer chrome (tweaks panel, aurora). Layout itself is CSS, which jsdom does not
// apply, so these assert the state and DOM the CSS keys off.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";
import { TWEAK_DEFAULTS, useUiStore } from "./stores/ui";

function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function appEl(container: HTMLElement): HTMLElement {
  return container.querySelector(".app") as HTMLElement;
}

describe("retired developer chrome", () => {
  afterEach(() => {
    cleanup();
    useUiStore.setState({ tweaks: TWEAK_DEFAULTS });
  });

  it("renders no tweaks panel and no aurora", () => {
    const { container } = renderApp("/team/espn:t1");
    expect(container.querySelector(".aurora")).toBeNull();
    expect(container.querySelector(".twk-gear")).toBeNull();
  });

  it("ignores persisted tweak values instead of writing them onto the root", () => {
    // A wall display may still carry tweaks from before; with no panel to change them
    // they must not keep silently resizing the layout.
    useUiStore.setState({ tweaks: { ...TWEAK_DEFAULTS, sidebarWidth: 300, rowHeight: 80 } });
    renderApp();
    expect(document.documentElement.style.getPropertyValue("--sidebar-w")).toBe("");
    expect(document.documentElement.style.getPropertyValue("--row-h")).toBe("");
  });
});

describe("sidebar collapse", () => {
  afterEach(() => {
    cleanup();
    useUiStore.setState({ sidebarCollapsed: false });
  });

  it("starts expanded, with no data-sidebar attribute", () => {
    const { container } = renderApp();
    expect(appEl(container).getAttribute("data-sidebar")).toBeNull();
  });

  it("collapses to the icon rail and back from the toggle", () => {
    const { container } = renderApp();

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(appEl(container).getAttribute("data-sidebar")).toBe("collapsed");

    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(appEl(container).getAttribute("data-sidebar")).toBeNull();
  });

  it("keeps the toggle reachable while collapsed, and reports state to assistive tech", () => {
    renderApp();

    const toggle = () => screen.getByRole("button", { name: /sidebar$/ });
    expect(toggle().getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(toggle());

    // Still operable: a collapse the user cannot undo from the collapsed state would be
    // a one-way door.
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
    expect(toggle().getAttribute("aria-label")).toBe("Expand sidebar");
  });

  it("restores a persisted collapsed state on mount", () => {
    // The wall display is restarted by a LaunchAgent; a collapse that reset every time
    // would have to be redone on every restart.
    useUiStore.setState({ sidebarCollapsed: true });
    const { container } = renderApp();
    expect(appEl(container).getAttribute("data-sidebar")).toBe("collapsed");
  });
});

describe("phone tab bar", () => {
  afterEach(cleanup);

  function tabbar(): HTMLElement {
    return document.querySelector(".tabbar") as HTMLElement;
  }

  it("offers all three destinations at once, with no drawer", () => {
    renderApp();
    const bar = within(tabbar());
    expect(bar.getByRole("link", { name: /Game Day/ })).toBeTruthy();
    expect(bar.getByRole("link", { name: /Teams/ })).toBeTruthy();
    expect(bar.getByRole("link", { name: /Settings/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open navigation" })).toBeNull();
  });

  it("marks Game Day current on the index route", () => {
    renderApp("/");
    const gameDay = within(tabbar()).getByRole("link", { name: /Game Day/ });
    expect(gameDay.className).toContain("active");
  });

  it("marks Teams current on any team route", () => {
    renderApp("/team/espn:t1/season");
    const teams = within(tabbar()).getByRole("link", { name: /Teams/ });
    expect(teams.getAttribute("aria-current")).toBe("page");
  });
});
