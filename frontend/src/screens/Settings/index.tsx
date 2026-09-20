// Screen 5: Settings — ported from design/screen-settings.jsx. All six prototype
// groups are wired up (task 7.3-7.7): Connected Platforms, one Leagues group per
// platform (Yahoo then ESPN, matching Connected Platforms' order), ESPN
// Credentials, Preferences, Appearance, Data Management, in prototype order.

import { useRef } from "react";

import { AppearanceCard } from "./AppearanceCard";
import { ConnectionsCard } from "./ConnectionsCard";
import { DataManagementCard } from "./DataManagementCard";
import { EspnCredentialsCard } from "./EspnCredentialsCard";
import { LeaguesCard } from "./LeaguesCard";
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
        <LeaguesCard platform="yahoo" />
        <LeaguesCard platform="espn" />
        <EspnCredentialsCard ref={swidInputRef} />
        <PreferencesCard />
        <AppearanceCard />
        <DataManagementCard />
      </div>
    </>
  );
}
