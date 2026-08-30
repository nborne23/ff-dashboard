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
  /**
   * Clamp `confidencePct` to [50, 99] — the "floored, favorite view". Defaults to
   * `true`, so every existing caller keeps its current behavior.
   *
   * The floor exists because a single-matchup surface (Head-to-Head) reads better
   * stating how confident the favorite is than announcing "you probably lose"; the
   * prototype's confidence badge never showed a sub-50 number.
   *
   * Game Day opts out (`clamp: false`). It renders six matchups at once, and six
   * panels each reading >= 50% would tell the user they are favored in every league
   * while two are lost — the floor stops being a presentation choice and becomes a
   * false claim (design D7). Unclamped, the raw rounded percent is returned with
   * neither the 50 floor nor the 99 ceiling.
   */
  clamp?: boolean;
}

export interface ProjectedFinalResult {
  mySigma: number;
  oppSigma: number;
  myFloor: number;
  myCeiling: number;
  oppFloor: number;
  oppCeiling: number;
  /**
   * Win probability for "my" side as a whole-number percent — clamped to [50, 99] by
   * default, or the raw rounded value when `clamp: false`.
   */
  confidencePct: number;
}

export function computeProjectedFinal({
  myProj,
  oppProj,
  myRemaining,
  oppRemaining,
  clamp = true,
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
  // Clamped (the default) this is intentionally one-sided-friendly per spec: it always
  // reads >= 50 (a "floored, favorite view"), even when the raw model favors the
  // opponent — mirroring the prototype's confidence badge, which never shows "my team
  // probably loses." Multi-matchup views pass `clamp: false` to get the true value; see
  // the `clamp` doc on ProjectedFinalInput.
  const rounded = Math.round(rawPct);
  const confidencePct = clamp ? Math.min(99, Math.max(50, rounded)) : rounded;

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
