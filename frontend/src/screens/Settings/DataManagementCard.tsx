// "Data Management" settings-group — matches design/screen-settings.jsx's Data
// Management group. "Refresh all data" reuses the Topbar's useRefresh; "Disconnect all
// platforms" reuses ConnectionsCard's confirm-then-DELETE pattern for both platforms.

import { getApiErrorMessage } from "../../api/client";
import { useRefresh } from "../../api/admin";
import { useDisconnect } from "../../api/connections";
import { useClearCache, useExportData } from "../../api/dataManagement";
import { SettingsRow } from "./SettingsRow";
import { useLastRefreshStatus } from "./useLastRefreshStatus";

export function DataManagementCard() {
  const refresh = useRefresh();
  const clearCache = useClearCache();
  const exportData = useExportData();
  const disconnectYahoo = useDisconnect("yahoo");
  const disconnectEspn = useDisconnect("espn");
  const lastRefresh = useLastRefreshStatus();

  const disconnecting = disconnectYahoo.isPending || disconnectEspn.isPending;

  const handleDisconnectAll = () => {
    if (!window.confirm("Disconnect all platforms? This deletes every stored credential.")) {
      return;
    }
    disconnectYahoo.mutate();
    disconnectEspn.mutate();
  };

  return (
    <div className="settings-group">
      <h3>Data Management</h3>
      {lastRefresh && (
        <SettingsRow
          label="Last refresh"
          sub={
            <span style={lastRefresh.isError ? { color: "var(--espn)" } : undefined}>
              {lastRefresh.label}
            </span>
          }
        />
      )}
      <SettingsRow
        label="Refresh all data"
        sub="Force a full re-sync from connected platforms"
        right={
          <button
            className="btn"
            type="button"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            {refresh.isPending ? "Refreshing…" : "Refresh"}
          </button>
        }
      />
      <SettingsRow
        label="Clear cache"
        sub={
          clearCache.isError
            ? getApiErrorMessage(clearCache.error, "Couldn't clear the cache.")
            : "Delete all cached upstream responses"
        }
        right={
          <button
            className="btn"
            type="button"
            disabled={clearCache.isPending}
            onClick={() => clearCache.mutate()}
          >
            Clear
          </button>
        }
      />
      <SettingsRow
        label="Export data"
        sub={
          exportData.isError
            ? getApiErrorMessage(exportData.error, "Couldn't export data.")
            : "Download teams, rosters, scoring as JSON"
        }
        right={
          <button
            className="btn"
            type="button"
            disabled={exportData.isPending}
            onClick={() => exportData.mutate()}
          >
            Export JSON
          </button>
        }
      />
      <SettingsRow
        label={<span style={{ color: "var(--espn)" }}>Disconnect all platforms</span>}
        right={
          <button
            className="btn danger"
            type="button"
            disabled={disconnecting}
            onClick={handleDisconnectAll}
          >
            Disconnect
          </button>
        }
      />
    </div>
  );
}
