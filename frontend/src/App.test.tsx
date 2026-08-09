// Task 10.5: verifies the TweaksPanel's sidebar-width and aurora-intensity sliders
// actually flow through the ui store into rendered CSS output (App.tsx's effect that
// sets `--sidebar-w`, and the `auroraColorForPath`-derived `--aurora-color`). Both were
// already wired on inspection; this locks that in with an assertion instead of relying
// on eyeballing the prototype.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";
import { TWEAK_DEFAULTS, useUiStore } from "./stores/ui";

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
