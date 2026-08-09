// Screen 5: Settings — ported from design/screen-settings.jsx. All six prototype
// groups are wired up (task 7.3-7.7): Connected Platforms, ESPN Leagues, ESPN
// Credentials, Preferences, Appearance, Data Management, in prototype order.

import { useRef } from "react";

import { AppearanceCard } from "./AppearanceCard";
import { ConnectionsCard } from "./ConnectionsCard";
import { DataManagementCard } from "./DataManagementCard";
import { EspnCredentialsCard } from "./EspnCredentialsCard";
import { EspnLeaguesCard } from "./EspnLeaguesCard";
import { PreferencesCard } from "./PreferencesCard";

export default function Settings() {
  const swidInputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <h1 className="large-title" style={{ textAlign: "left" }}>
        Settings
      </h1>
      <p className="large-subtitle">Account, leagues, and preferences</p>

      <div className="settings-page">
        <ConnectionsCard
          onEspnConnectRequested={() => {
            const input = swidInputRef.current;
            input?.focus();
            input?.scrollIntoView?.({ behavior: "smooth", block: "center" });
          }}
        />
        <EspnLeaguesCard />
        <EspnCredentialsCard ref={swidInputRef} />
        <PreferencesCard />
        <AppearanceCard />
        <DataManagementCard />
      </div>
    </>
  );
}
