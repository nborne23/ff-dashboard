# GridIron — Apple design audit

Audited 2026-10-22 against the Apple design skill (WWDC *Designing Fluid Interfaces*,
*The Details of UI Typography*, *Principles of Great Design*) and the ten problems in
`claude-design-brief.md`. Screens reviewed live at 375×812 and 1440×900: Game Day, My
Team, Matchup, Season, Waivers, League, Settings.

Severity: **P1** breaks understanding or trust · **P2** costs clarity on every glance ·
**P3** craft.

## Navigation and wayfinding

| # | Sev | Finding | Principle |
|---|---|---|---|
| N1 | P1 | Two nav systems for one axis. Sidebar lists Matchups / Season / Waivers / League; the in-page tabs list the same five. Neither is clearly "the" way. (Brief #1) | Familiarity: one thing, one place |
| N2 | P1 | The sidebar's team-scoped links show no team and silently resolve to whichever team you last viewed. "Waivers" goes somewhere different depending on history. (Brief #2) | Wayfinding: *where will this take me?* |
| N3 | P2 | The six teams sit behind a "My Teams" disclosure. Reaching one team's view is expand → team → tab. (Brief #4) | Simplicity: common path first |
| N4 | P2 | Sidebar links render underlined, like browser-default links. They read as prose, not controls. | Craft |
| N5 | P3 | The phone uses a hamburger drawer for a three-destination app. A tab bar would show every destination with no tap. | Familiarity (iOS tab bar) |

## Color and meaning

| # | Sev | Finding | Principle |
|---|---|---|---|
| C1 | P1 | Pink means both "points" (category) and "you're losing" (valence). Green means both "projected" and "winning". Score labels are pink for *me* and cyan for *them*, so on a losing panel my own name is pink next to a red margin. (Brief #5) | Clarity: one color, one meaning |
| C2 | P2 | A per-route aurora tint (orange, purple, cyan, gray, pink) repaints the chrome on every screen with no meaning attached. | Purpose: every element earns its place |
| C3 | P2 | Platform colors (ESPN red, Yahoo purple) sit next to valence red and the pink accent, so the eye can't sort them. | Clarity |

## Typography

| # | Sev | Finding | Principle |
|---|---|---|---|
| T1 | P1 | Meaningful text below the brief's own 15px floor: stat-strip labels (11px small caps), slot labels and slot diffs (~10px), player meta (12px), nav-group labels (11px). | Legibility at distance |
| T2 | P2 | One global `letter-spacing: -0.01em` on body. Tracking should vary with size: negative on display, about 0 on body, slightly positive on small caps. | §15 size-specific tracking |
| T3 | P2 | Sizes are hard-coded px throughout ~2,400 lines of CSS, so the user's text size setting can't scale the layout. | §15 respect Dynamic Type |
| T4 | P3 | No type scale. Sizes are picked per component (11, 12, 13, 14, 15, 17, 22, 28, 34, 40…). | Craft: nothing random |

## Game Day panel

| # | Sev | Finding | Principle |
|---|---|---|---|
| G1 | P1 | The uppercase team labels above the scores repeat the header's team name and truncate ("PEA PE…", "SCRANTON STRAN…"), so the opponent is unreadable. | Simplicity |
| G2 | P2 | PROJECTED / WIN PROB / YET TO PLAY carry equal weight. Win probability answers "am I winning?" and should lead. The "vs" values collide with the label row at narrow widths. (Brief #8) | Hierarchy |
| G3 | P2 | Slot labels show backend names: `K1`, `FLEX2`, `WR1`. (Brief #6) | Plain language |
| G4 | P2 | A 0.0 that hasn't kicked off and a 0.0 that was shut out differ only by a faint dim. The payload only has `pre`/`in`/`post` per player, not the clock or the opponent, so state is the most it can say. (Brief #7) | Feedback: status |
| G5 | P2 | Reordering uses HTML5 drag-and-drop: a ghost image and no 1:1 tracking. The resize handle cycles spans on pointer-down with no preview. | §2 direct manipulation |
| G6 | P3 | The spotlight overlay appears with no spatial origin. It should grow from the panel that opened it and return there. | §7 spatial consistency |
| G7 | P3 | The "Expand all / Collapse all" and arrangement controls are setup affordances, but they get the same visual weight as the content. | Purpose |

## Chrome and materials

| # | Sev | Finding | Principle |
|---|---|---|---|
| M1 | P1 | The freshness label reads "Last updated 46292m ago": no hour or day units. It also appears twice, in the topbar and the sidebar footer. | Feedback: status |
| M2 | P2 | The "0 LIVE" badge stays on screen when nothing is live. The day-rings strip shows "!" glyphs with no explanation. | Utility: feedback only where it earns it |
| M3 | P2 | The topbar is opaque black with a hard 0.5px rule. Chrome should be a translucent material with a scroll-edge fade. | §12 materials |
| M4 | P2 | The floating tweaks gear (sidebar width, row height, sparkline thickness, aurora intensity) is a developer tool in a user's room. (Brief #10) | Purpose |
| M5 | P3 | There is no `prefers-reduced-transparency` or `prefers-contrast` handling. Only reduced motion is covered. | §14 |

## Interaction feedback

| # | Sev | Finding | Principle |
|---|---|---|---|
| I1 | P2 | Most buttons, tabs, segmented controls and rows have hover styles only. There's no press state, so nothing responds on pointer-down. | §1 respond on press |
| I2 | P3 | Focus rings are browser defaults or missing. | Agency, accessibility |

## Screens

| # | Sev | Finding |
|---|---|---|
| S1 | P2 | Settings is seven stacked cards in a column. Grouped inset lists with plain section headers say the same thing with less chrome. (Brief #9) |
| S2 | P2 | The Appearance card's Light/Auto theme toggle is persisted but never applied. The app is dark-only by brief, so the control lies. |
| S3 | P3 | Season's "cyan = win, pink = loss" legend is a third valence mapping. |

## Out of scope (data, not design)

- Season shows a **0–3** record while League shows the same team at **1–0**. Season appears to count weeks 0–2 including unplayed ones. File separately.

---

# Redesign: what changed

**Navigation (N1–N5).** Sidebar is now Game Day, every team by name with its live
margin (a six-line scoreboard), and Settings. A team's views live only in the team
header's segmented control. Picking another team keeps the current view. On a phone a
bottom tab bar (Game Day · Teams · Settings) replaces the hamburger drawer.

**Color (C1–C3, S3).** Every color has one job (`tokens.css`): blue for accent and
"you", green for winning, red for losing and errors, orange for live, gray for the
opponent. Platform pills are neutral. The aurora tint is gone. Season's legend now
reads "green won, red lost".

**Type (T1–T4).** One rem-based scale (score, large title, title 1–3, headline, body,
callout, subhead, footnote, caption) with size-specific tracking and leading. 15px is
the floor for values in Game Day panels at 2-across and wider. Slot labels (12px caps)
and roster rows below 540px panel width are the documented exceptions.

**Game Day (G1–G7).**
- Opponent named under their score. Redundant uppercase labels removed.
- Win probability leads, with a valence-colored meter.
- Slot labels humanized (`FLEX2` → `FLEX`, `DST` → `D/ST`), here and on Roster and
  Matchup.
- Reorder drag shows a lifted source and a drop target.
- Re-sorts, drags and arrangement changes glide via interruptible FLIP on spring
  curves.
- Spotlight grows out of its panel and returns there.
- Controls are quieter.
- Full-width on the wall display.

**Chrome and materials (M1–M5).**
- Freshness has one home, the topbar, and shows h/d units.
- The live badge appears only when something is live.
- Day rings and the tweaks panel are removed.
- The topbar is a translucent material with a scroll-edge fade.
- Reduced-transparency and increased-contrast fallbacks added.

**Feedback (I1–I2).** Press scale on pointer-down for all controls, and one keyboard
focus ring.

**Settings (S1–S2).** Inset grouped lists, iOS style, in two columns: accounts and app
behavior. The unwired theme toggle and accent swatches are removed. The app is
dark-only.

**Still open.**
- G4/brief #7: per-player game clock and NFL opponent need new payload fields.
- G5: reorder is still HTML5 drag-and-drop with visual feedback, not true 1:1 pointer
  tracking.
- The Season 0–3 vs League 1–0 data bug.
