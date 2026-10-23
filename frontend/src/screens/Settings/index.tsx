// Settings: inset grouped lists in two columns. Left is accounts (platforms, ESPN
// credentials, which leagues to follow); right is how the app behaves (refresh cadence,
// data). Appearance is gone: the app is dark-only by design, and a theme switch that
// never changed the theme was a control that lied.

import { useRef } from "react";

import { ConnectionsCard } from "./ConnectionsCard";
import { DataManagementCard } from "./DataManagementCard";
import { EspnCredentialsCard } from "./EspnCredentialsCard";
import { LeaguesCard } from "./LeaguesCard";
import { PreferencesCard } from "./PreferencesCard";

export default function Settings() {
  const swidInputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <h1 className="large-title">Settings</h1>
      <p className="large-subtitle">Accounts, leagues, and how GridIron refreshes</p>

      <div className="settings-page">
        <div className="settings-col">
          <ConnectionsCard
            onEspnConnectRequested={() => {
              const input = swidInputRef.current;
              input?.focus();
              input?.scrollIntoView?.({ behavior: "smooth", block: "center" });
            }}
          />
          <EspnCredentialsCard ref={swidInputRef} />
          <LeaguesCard platform="yahoo" />
          <LeaguesCard platform="espn" />
        </div>
        <div className="settings-col">
          <PreferencesCard />
          <DataManagementCard />
        </div>
      </div>
    </>
  );
}
