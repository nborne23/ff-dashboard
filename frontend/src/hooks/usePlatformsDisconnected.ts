// Shared "should this screen show the connect-a-platform empty state" signal (task
// 10.3). MyTeam/HeadToHead/Season are all reached via a specific team id in the URL, so
// their primary query can 404 ("team not found") before it ever gets a chance to read
// `meta.platforms` off a successful envelope — the dedicated `/api/connections` query is
// what lets those screens tell "nothing is connected" apart from "this team id is bad".

import { useConnections } from "../api/connections";
import type { Meta } from "../types/api";

/**
 * True once there's positive evidence neither platform is connected: either the
 * caller's own envelope `meta.platforms` says so (both `error === "not_connected"`), or
 * the dedicated connections query says so (both `is_connected === false`). Returns
 * `false` while undetermined — callers should treat `false` as "not yet known to be
 * disconnected", not "definitely connected".
 */
export function usePlatformsDisconnected(meta?: Meta | null): boolean {
  const connectionsQuery = useConnections();

  const metaSaysDisconnected = Boolean(
    meta &&
    meta.platforms.yahoo?.error === "not_connected" &&
    meta.platforms.espn?.error === "not_connected",
  );

  const connections = connectionsQuery.data;
  const connectionsSayDisconnected = Boolean(
    connections && !connections.yahoo.is_connected && !connections.espn.is_connected,
  );

  return metaSaysDisconnected || connectionsSayDisconnected;
}
