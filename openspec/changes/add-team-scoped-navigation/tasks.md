# Tasks

## 1. Route model

- [x] 1.1 Add `hooks/teamRoute.ts`: `parseTeamRoute`, `teamRoutePath`, `resolveTeamId`, `TEAM_SECTIONS`
- [x] 1.2 Unit tests, including the stale-id fallback and the percent-encoded id

## 2. Remembered team

- [x] 2.1 Add persisted `activeTeamId` to the ui store
- [x] 2.2 Add `useActiveTeamSync()` writing it from the route, and call it in `App`

## 3. Shell

- [x] 3.1 Point the sidebar's Matchups/Season links at the resolved team
- [x] 3.2 Highlight the active team across all three of its views; open the group on arrival
- [x] 3.3 Add `TeamContextBar` (switcher + section tabs) and render it from `App`
- [x] 3.4 Styles, including the phone stack below 768px

## 4. Verification

- [x] 4.1 Component tests: tab navigation, section-preserving team switch, disabled switcher
- [x] 4.2 Measure at 375/390/1400px — zero overflow, bar absent on league-wide routes
- [ ] 4.3 Acceptance on the iMac deployment from a phone
