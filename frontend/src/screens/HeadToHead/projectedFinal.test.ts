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
