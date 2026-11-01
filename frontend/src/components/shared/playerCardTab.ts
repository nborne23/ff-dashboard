// Which tab the player card opens on: the last one chosen, for the rest of the page's
// life — scanning five waiver targets' game logs shouldn't take a tab tap per player.
// Its own module so PlayerStatsPanel.tsx exports components only (fast refresh).

export type PlayerCardTab = "overview" | "gamelog" | "stats";

let remembered: PlayerCardTab = "overview";

export function rememberedPlayerCardTab(): PlayerCardTab {
  return remembered;
}

export function rememberPlayerCardTab(tab: PlayerCardTab) {
  remembered = tab;
}

/** Test hook: put the card back on its first-open tab. */
export function resetPlayerCardTab() {
  remembered = "overview";
}
