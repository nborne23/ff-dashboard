// "Connected Platforms" settings-group — matches design/screen-settings.jsx's
// Yahoo/ESPN rows. Toggling Yahoo on kicks off the OAuth redirect; toggling
// either platform off deletes its stored credentials (confirmed first, since
// that's destructive). Toggling ESPN on doesn't call the API — ESPN has no
// OAuth flow, so it just hands focus to the credentials card below.

import { getApiErrorMessage } from "../../api/client";
import type { ConnectionStatus, Platform } from "../../api/connections";
import { useConnections, useDisconnect, useYahooStart } from "../../api/connections";
import { formatRelativeTime } from "./formatRelativeTime";
import { SettingsRow, SkeletonRow } from "./SettingsRow";
import { Switch } from "./Switch";

interface ConnectionsCardProps {
  onEspnConnectRequested: () => void;
}

const PLATFORM_META: Record<Platform, { pillClass: string; pillLabel: string; name: string }> = {
  yahoo: { pillClass: "pill yahoo", pillLabel: "YAHOO", name: "Yahoo Fantasy" },
  espn: { pillClass: "pill espn", pillLabel: "ESPN", name: "ESPN Fantasy" },
};

function connectionSub(status: ConnectionStatus): string {
  if (!status.is_connected) return "Not connected";
  const relative = formatRelativeTime(status.last_verified_at);
  const parts = [status.display_name ? `Connected as ${status.display_name}` : "Connected"];
  if (relative) parts.push(`verified ${relative}`);
  return parts.join(" · ");
}

function PlatformRow({
  status,
  disabled,
  onToggle,
}: {
  status: ConnectionStatus;
  disabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  const meta = PLATFORM_META[status.platform];
  return (
    <SettingsRow
      label={
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className={meta.pillClass}>{meta.pillLabel}</span>
          <span>{meta.name}</span>
        </span>
      }
      sub={connectionSub(status)}
      right={
        <Switch
          on={status.is_connected}
          onChange={onToggle}
          disabled={disabled}
          label={`${meta.name} connection`}
        />
      }
    />
  );
}

export function ConnectionsCard({ onEspnConnectRequested }: ConnectionsCardProps) {
  const connectionsQuery = useConnections();
  const yahooStart = useYahooStart();
  const disconnectYahoo = useDisconnect("yahoo");
  const disconnectEspn = useDisconnect("espn");

  const handleYahooToggle = (next: boolean) => {
    if (next) {
      yahooStart.mutate(undefined, {
        onSuccess: (data) => {
          window.location.assign(data.auth_url);
        },
      });
      return;
    }
    if (window.confirm("Disconnect Yahoo Fantasy? This deletes your stored access tokens.")) {
      disconnectYahoo.mutate();
    }
  };

  const handleEspnToggle = (next: boolean) => {
    if (next) {
      onEspnConnectRequested();
      return;
    }
    if (window.confirm("Disconnect ESPN Fantasy? This deletes your stored credentials.")) {
      disconnectEspn.mutate();
    }
  };

  return (
    <div className="settings-group">
      <h3>Connected Platforms</h3>

      {connectionsQuery.isLoading && (
        <>
          <SkeletonRow />
          <SkeletonRow />
        </>
      )}

      {connectionsQuery.isError && (
        <SettingsRow
          label="Couldn't load connections"
          sub={getApiErrorMessage(connectionsQuery.error, "Check your connection and try again.")}
        />
      )}

      {connectionsQuery.data && (
        <>
          <PlatformRow
            status={connectionsQuery.data.yahoo}
            disabled={yahooStart.isPending || disconnectYahoo.isPending}
            onToggle={handleYahooToggle}
          />
          <PlatformRow
            status={connectionsQuery.data.espn}
            disabled={disconnectEspn.isPending}
            onToggle={handleEspnToggle}
          />
        </>
      )}
    </div>
  );
}
