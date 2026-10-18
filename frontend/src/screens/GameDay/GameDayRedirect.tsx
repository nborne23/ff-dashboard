import { Navigate, useLocation } from "react-router-dom";

/** Game Day moved to "/", so the old path redirects there rather than rendering a second
 * copy of the screen — one URL per screen keeps the sidebar's active state unambiguous.
 * The search string carries through; a `?week=` in it is ignored — every load lands on the
 * current week (hooks/useCurrentWeekDefault.ts). */
export default function GameDayRedirect() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: "/", search }} replace />;
}
