/**
 * The slot as a person would say it. The backend numbers every repeated slot (`WR1`,
 * `FLEX2`, `K1`) to keep them unique, but row order already distinguishes two receivers,
 * so the number is noise. `DST` gets the slash every fantasy site prints.
 */
export function displaySlot(slot: string): string {
  const base = slot.replace(/\d+$/, "");
  return base === "DST" ? "D/ST" : base;
}
