import { describe, expect, it } from "vitest";

import { computeProjectedFinal } from "./projectedFinal";

describe("computeProjectedFinal", () => {
  it("widens sigma with sqrt(remaining) and computes proj +/- sigma as floor/ceiling", () => {
    const result = computeProjectedFinal({
      myProj: 100,
      oppProj: 90,
      myRemaining: 4,
      oppRemaining: 1,
    });

    expect(result.mySigma).toBeCloseTo(24, 5); // 12 * sqrt(4)
    expect(result.oppSigma).toBeCloseTo(12, 5); // 12 * sqrt(1)
    expect(result.myFloor).toBeCloseTo(76, 5);
    expect(result.myCeiling).toBeCloseTo(124, 5);
    expect(result.oppFloor).toBeCloseTo(78, 5);
    expect(result.oppCeiling).toBeCloseTo(102, 5);
  });

  it("returns a high (but clamped <= 99) confidence when heavily favored", () => {
    const result = computeProjectedFinal({
      myProj: 150,
      oppProj: 50,
      myRemaining: 0,
      oppRemaining: 0,
    });

    expect(result.confidencePct).toBe(99);
  });

  it("floors confidence at 50 even when trailing badly (never reports < 50)", () => {
    const result = computeProjectedFinal({
      myProj: 50,
      oppProj: 150,
      myRemaining: 0,
      oppRemaining: 0,
    });

    expect(result.confidencePct).toBe(50);
  });

  it("reports ~50 for an exact tie with equal remaining uncertainty", () => {
    const result = computeProjectedFinal({
      myProj: 100,
      oppProj: 100,
      myRemaining: 3,
      oppRemaining: 3,
    });

    expect(result.confidencePct).toBe(50);
  });

  it("does not divide by zero (NaN) when both sides have 0 remaining and scores differ", () => {
    const result = computeProjectedFinal({
      myProj: 120,
      oppProj: 100,
      myRemaining: 0,
      oppRemaining: 0,
    });

    expect(Number.isNaN(result.confidencePct)).toBe(false);
    expect(result.confidencePct).toBe(99);
  });

  it("does not divide by zero when both sides have 0 remaining and scores are tied", () => {
    const result = computeProjectedFinal({
      myProj: 100,
      oppProj: 100,
      myRemaining: 0,
      oppRemaining: 0,
    });

    expect(Number.isNaN(result.confidencePct)).toBe(false);
    expect(result.confidencePct).toBe(50);
  });

  it("increases confidence as my lead grows, holding remaining counts fixed", () => {
    const small = computeProjectedFinal({
      myProj: 105,
      oppProj: 100,
      myRemaining: 2,
      oppRemaining: 2,
    });
    const large = computeProjectedFinal({
      myProj: 130,
      oppProj: 100,
      myRemaining: 2,
      oppRemaining: 2,
    });

    expect(large.confidencePct).toBeGreaterThanOrEqual(small.confidencePct);
  });
});

describe("computeProjectedFinal clamp option (design D7)", () => {
  // A clearly losing matchup: 30 points behind with only a couple of players left, so
  // the raw model is well under 50%.
  const losing = {
    myProj: 90,
    oppProj: 120,
    myRemaining: 2,
    oppRemaining: 2,
  };

  it("floors at 50 by default, preserving the existing favorite view", () => {
    expect(computeProjectedFinal(losing).confidencePct).toBe(50);
  });

  it("floors at 50 when clamp is passed explicitly", () => {
    expect(computeProjectedFinal({ ...losing, clamp: true }).confidencePct).toBe(50);
  });

  it("returns the true sub-50 probability when clamp is false", () => {
    const raw = computeProjectedFinal({ ...losing, clamp: false }).confidencePct;
    expect(raw).toBeLessThan(50);
    expect(raw).toBeGreaterThan(0);
  });

  it("drops the 99 ceiling too, not just the 50 floor", () => {
    const winning = { myProj: 160, oppProj: 80, myRemaining: 1, oppRemaining: 1 };
    expect(computeProjectedFinal({ ...winning, clamp: true }).confidencePct).toBe(99);
    expect(computeProjectedFinal({ ...winning, clamp: false }).confidencePct).toBe(100);
  });

  it("agrees with the clamped value whenever the raw value is already inside [50, 99]", () => {
    const close = { myProj: 112, oppProj: 105, myRemaining: 4, oppRemaining: 4 };
    const clamped = computeProjectedFinal({ ...close, clamp: true }).confidencePct;
    const unclamped = computeProjectedFinal({ ...close, clamp: false }).confidencePct;
    expect(unclamped).toBeGreaterThan(50);
    expect(unclamped).toBeLessThan(99);
    expect(clamped).toBe(unclamped);
  });

  it("leaves the non-probability outputs untouched", () => {
    const a = computeProjectedFinal({ ...losing, clamp: true });
    const b = computeProjectedFinal({ ...losing, clamp: false });
    expect(b.mySigma).toBe(a.mySigma);
    expect(b.myFloor).toBe(a.myFloor);
    expect(b.oppCeiling).toBe(a.oppCeiling);
  });
});
