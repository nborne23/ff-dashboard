// "ESPN Credentials" settings-group — matches design/screen-settings.jsx's
// SWID/espn_s2 field-rows plus a "Test Connection" row. POST
// /api/connections/espn/test both verifies the cookies against ESPN *and*
// persists them on success (see backend/gridiron/api/connections.py), so a
// successful test doubles as "connect".

import { forwardRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { getApiErrorMessage } from "../../api/client";
import { useEspnTest } from "../../api/connections";
import { formatRelativeTime } from "./formatRelativeTime";
import { SettingsRow } from "./SettingsRow";

const FIELD_ROW_STYLE = { borderBottom: "0.5px solid var(--separator)" };

export const EspnCredentialsCard = forwardRef<HTMLInputElement>(
  function EspnCredentialsCard(_props, swidInputRef) {
    const [swid, setSwid] = useState("");
    const [espnS2, setEspnS2] = useState("");
    const espnTest = useEspnTest();

    const handleSubmit = (event: FormEvent) => {
      event.preventDefault();
      espnTest.mutate({ swid, espn_s2: espnS2 });
    };

    let statusNode: ReactNode = null;
    if (espnTest.isPending) {
      statusNode = <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>Testing…</span>;
    } else if (espnTest.isError) {
      statusNode = (
        <span style={{ color: "var(--espn)", fontSize: 13 }}>
          {getApiErrorMessage(espnTest.error, "ESPN rejected the provided cookies.")}
        </span>
      );
    } else if (espnTest.isSuccess) {
      const relative = formatRelativeTime(espnTest.data.last_verified_at) ?? "just now";
      statusNode = (
        <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>Connected · {relative}</span>
      );
    }

    return (
      <div className="settings-group">
        <h3>ESPN Credentials</h3>
        <form onSubmit={handleSubmit}>
          <div className="field-row" style={FIELD_ROW_STYLE}>
            <div className="label">SWID</div>
            <input
              ref={swidInputRef}
              type="text"
              aria-label="SWID"
              placeholder="{xxxx-xxxx-xxxx}"
              value={swid}
              onChange={(event) => setSwid(event.target.value)}
            />
          </div>
          <div className="field-row" style={FIELD_ROW_STYLE}>
            <div className="label">espn_s2</div>
            <input
              type="password"
              aria-label="espn_s2"
              value={espnS2}
              onChange={(event) => setEspnS2(event.target.value)}
            />
          </div>
          <SettingsRow
            label={statusNode}
            right={
              <button
                className="btn"
                type="submit"
                disabled={espnTest.isPending || !swid || !espnS2}
              >
                Test Connection
              </button>
            }
          />
        </form>
      </div>
    );
  },
);
