import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LOGO_MIN_SIZE, TeamLogo } from "./TeamLogo";

describe("TeamLogo", () => {
  afterEach(cleanup);

  it("renders the image when a logo url is present", () => {
    render(<TeamLogo team={{ name: "Bing Bong", logo_url: "/api/team-logos/espn/l-1-t-2" }} />);

    const img = screen.getByRole("presentation", { hidden: true }) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("/api/team-logos/espn/l-1-t-2");
  });

  it("renders initials without an <img> when logo_url is null", () => {
    // No request at all: the backend would only answer with a crest, and asking for it
    // costs a round trip per team on a ten-row standings table.
    render(<TeamLogo team={{ name: "Scarecrow Boat", logo_url: null }} />);

    expect(screen.getByTestId("team-logo-fallback").textContent).toBe("SB");
    expect(document.querySelector("img")).toBeNull();
  });

  it("falls back to initials when the image fails to load", () => {
    render(<TeamLogo team={{ name: "Fresh Meat", logo_url: "/api/team-logos/espn/gone" }} />);

    fireEvent.error(screen.getByRole("presentation", { hidden: true }));

    expect(screen.getByTestId("team-logo-fallback").textContent).toBe("FM");
    expect(document.querySelector("img")).toBeNull();
  });

  it("honors a requested size at or above the floor", () => {
    render(<TeamLogo team={{ name: "Garbage", logo_url: null }} size={32} />);

    const el = screen.getByTestId("team-logo-fallback");
    expect(el.style.width).toBe("32px");
    expect(el.style.height).toBe("32px");
  });

  it("clamps a size below the legibility floor", () => {
    // 43% of these avatars are photographs — a 14px one is a coloured smudge, not an
    // identity. The floor is enforced here rather than trusted at each call site,
    // because the tempting fix for a tight row is exactly to pass a smaller number.
    render(<TeamLogo team={{ name: "Garbage", logo_url: null }} size={14} />);

    const el = screen.getByTestId("team-logo-fallback");
    expect(el.style.width).toBe(`${LOGO_MIN_SIZE}px`);
    expect(LOGO_MIN_SIZE).toBe(24);
  });

  it("draws no ring when none is requested", () => {
    render(<TeamLogo team={{ name: "Garbage", logo_url: null }} />);

    expect(screen.getByTestId("team-logo-fallback").style.boxShadow).toBe("");
  });

  it("draws the ring on the image path", () => {
    render(
      <TeamLogo
        team={{ name: "Bing Bong", logo_url: "/api/team-logos/espn/x" }}
        ringColor="var(--espn)"
      />,
    );

    const img = screen.getByRole("presentation", { hidden: true }) as HTMLImageElement;
    expect(img.style.boxShadow).toContain("var(--espn)");
  });

  it("draws the ring on the fallback path too", () => {
    // The fallback is the common case for teams with no logo, so a ring that only
    // appeared on <img> would silently drop the platform cue for exactly those rows.
    render(<TeamLogo team={{ name: "No Logo", logo_url: null }} ringColor="var(--yahoo)" />);

    expect(screen.getByTestId("team-logo-fallback").style.boxShadow).toContain("var(--yahoo)");
  });

  it("takes initials from a single-word name", () => {
    render(<TeamLogo team={{ name: "Garbage", logo_url: null }} />);

    expect(screen.getByTestId("team-logo-fallback").textContent).toBe("G");
  });
});
