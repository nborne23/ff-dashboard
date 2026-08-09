// Shared error state (task 10.2) — generalizes the near-identical
// `<div className="card">...<button className="btn primary">Retry</button></div>`
// block every data screen (Dashboard/MyTeam/HeadToHead/Season) was hand-rolling. Same
// DOM/classNames those already used (so no visual change), plus a `var(--espn)`-tinted
// icon up top.

import { getApiErrorMessage } from "../../api/client";
import { IconAlertCircle } from "../primitives";

export interface ErrorCardProps {
  /** The caught error (usually a TanStack Query `.error`) — fed straight to
   * `getApiErrorMessage` for a typed, human-readable message. */
  error: unknown;
  fallbackMessage?: string;
  onRetry: () => void;
  testId?: string;
}

export function ErrorCard({ error, fallbackMessage, onRetry, testId }: ErrorCardProps) {
  return (
    <div className="card" style={{ textAlign: "center", padding: 32 }} data-testid={testId}>
      <div
        style={{
          color: "var(--espn)",
          display: "flex",
          justifyContent: "center",
          marginBottom: 12,
        }}
      >
        <IconAlertCircle size={28} />
      </div>
      <p className="large-subtitle" style={{ marginBottom: 16 }}>
        {getApiErrorMessage(error, fallbackMessage)}
      </p>
      <button type="button" className="btn primary" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
