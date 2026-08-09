// Client-side projected-final math for the Head-to-Head "Projected Final"
// card and the top card's "Win Prob." stat (task 5.8/5.9). No backend
// endpoint computes this — it's a deliberately simple normal approximation
// derived entirely from data the H2H envelope already returns:
// matchup.home_proj/away_proj and remaining.mine/theirs.
//
// Model: each remaining (unplayed) starter contributes independent scoring
// variance with a fixed per-player standard deviation. A team's remaining
// uncertainty is sigma = SIGMA_PER_PLAYER * sqrt(remainingCount) (variances
// sum for independent players, so the combined sigma scales with sqrt(n)).
// Win probability is P(myFinal > oppFinal) under
// myFinal - oppFinal ~ Normal(myProj - oppProj, mySigma^2 + oppSigma^2),
// i.e. Phi((myProj - oppProj) / sqrt(mySigma^2 + oppSigma^2)).

/** Points of standard deviation contributed by one remaining (unplayed) starter. */
const SIGMA_PER_PLAYER = 12;

/**
 * Logistic approximation of the standard normal CDF: Phi(z) ~= 1 / (1 + e^(-1.702z)).
 * Chosen (over erf-based approximations) because it's a single closed-form
 * expression with no piecewise branches, so results are exactly reproducible
 * in tests.
 */
function normalCdfApprox(z: number): number {
  return 1 / (1 + Math.exp(-1.702 * z));
}

export interface ProjectedFinalInput {
  myProj: number;
  oppProj: number;
  myRemaining: number;
  oppRemaining: number;
}

export interface ProjectedFinalResult {
  mySigma: number;
  oppSigma: number;
  myFloor: number;
  myCeiling: number;
  oppFloor: number;
  oppCeiling: number;
  /** Win probability for "my" side, as a whole-number percent clamped to [50, 99]. */
  confidencePct: number;
}

export function computeProjectedFinal({
  myProj,
  oppProj,
  myRemaining,
  oppRemaining,
}: ProjectedFinalInput): ProjectedFinalResult {
  const mySigma = SIGMA_PER_PLAYER * Math.sqrt(Math.max(0, myRemaining));
  const oppSigma = SIGMA_PER_PLAYER * Math.sqrt(Math.max(0, oppRemaining));
  const diff = myProj - oppProj;
  const combinedSigma = Math.sqrt(mySigma * mySigma + oppSigma * oppSigma);

  // Guard the divide-by-zero when both sides are fully final (no remaining
  // players, sigma=0 on both sides): the outcome is deterministic, so z is
  // +/-Infinity (or 0 for an exact tie) rather than NaN from 0/0.
  const z =
    combinedSigma === 0 ? (diff === 0 ? 0 : diff > 0 ? Infinity : -Infinity) : diff / combinedSigma;

  const rawPct = normalCdfApprox(z) * 100;
  // Clamp is intentionally one-sided-friendly per spec: it always reads
  // >= 50 (a "floored, favorite view"), even when the raw model favors the
  // opponent — this mirrors the prototype's confidence badge, which never
  // shows "my team probably loses."
  const confidencePct = Math.min(99, Math.max(50, Math.round(rawPct)));

  return {
    mySigma,
    oppSigma,
    myFloor: myProj - mySigma,
    myCeiling: myProj + mySigma,
    oppFloor: oppProj - oppSigma,
    oppCeiling: oppProj + oppSigma,
    confidencePct,
  };
}
