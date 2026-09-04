// The detail behind an injury badge (add-player-health D1). Reuses the `.draft-detail-*`
// overlay shape rather than introducing a second dialog vocabulary — that panel is the
// app's only dialog, and it is already position:fixed, so this renders inline.
//
// A right-click context menu was considered and rejected: it has no touch equivalent,
// and this app is used on a phone and on a wall-mounted iMac as much as on a desktop.

import { useEffect } from "react";
import { createPortal } from "react-dom";

import { usePlayerInjury } from "../../api/players";
import type { InjuryStatus, PlayerInjuryReport } from "../../types/api";
import { INJURY_LABELS } from "./injuryLabels";

/** ESPN writes the literal string "Not Specified" into `details.*` rather than omitting
 *  the key, so an unfiltered render shows a "Side: Not Specified" row on most reports. */
function present(value: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed || trimmed.toLowerCase() === "not specified") return null;
  return trimmed;
}

function formatDate(raw: string | null): string | null {
  if (!raw) return null;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function Facts({ report }: { report: PlayerInjuryReport }) {
  const rows: Array<[string, string]> = [];
  const type = present(report.injury_type);
  const side = present(report.side);
  const location = present(report.location);
  const detail = present(report.detail);
  const returnDate = formatDate(present(report.return_date));

  if (type) rows.push(["Injury", side ? `${type} (${side})` : type]);
  if (location && location !== type) rows.push(["Area", location]);
  if (detail) rows.push(["Treatment", detail]);
  if (returnDate) rows.push(["Est. return", returnDate]);

  if (rows.length === 0) return null;
  return (
    <dl className="injury-facts">
      {rows.map(([label, value]) => (
        <div key={label} className="injury-fact">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export interface PlayerHealthPanelProps {
  playerId: string;
  playerName: string;
  status: InjuryStatus | null | undefined;
  onClose: () => void;
}

export function PlayerHealthPanel({
  playerId,
  playerName,
  status,
  onClose,
}: PlayerHealthPanelProps) {
  const { data, isLoading, isError } = usePlayerInjury(playerId, true);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lock the page behind the dialog. Without this the body keeps scrolling under a
  // bottom-anchored sheet, which on a phone reads as the panel sliding up the page
  // rather than as a modal — the exact symptom reported from iOS.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  const payload = data?.data;
  const report = payload?.report ?? null;
  const code = status && status !== "ACTIVE" ? status : null;

  // Rendered into <body> rather than in place. `position: fixed` is resolved against
  // the nearest ancestor with a transform/filter/contain — and this panel is mounted
  // from inside a table cell on four different screens, so any such ancestor added
  // anywhere above it would silently drop the dialog back into document flow. A portal
  // removes the whole class of failure instead of chasing each instance.
  return createPortal(
    <div
      className="draft-detail-overlay"
      onClick={onClose}
      data-testid="player-health-overlay"
      role="presentation"
    >
      <div
        className="draft-detail-panel card"
        onClick={(event) => event.stopPropagation()}
        data-testid="player-health-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${playerName} health detail`}
      >
        <div className="draft-detail-header">
          <div>
            <div className="player-name" style={{ fontSize: 18, fontWeight: 700 }}>
              {playerName}
            </div>
            <div className="player-meta">
              {code ? (INJURY_LABELS[code] ?? code) : "Health"}
              {report?.status && report.status !== (code ? INJURY_LABELS[code] : null)
                ? ` · ${report.status}`
                : ""}
            </div>
          </div>
          <button type="button" className="btn" onClick={onClose} aria-label="Close">
            Close
          </button>
        </div>

        {isLoading && <p className="muted">Loading…</p>}

        {isError && (
          <p className="muted">Couldn’t load the health report. It’ll retry on reopen.</p>
        )}

        {!isLoading && !isError && report && (
          <>
            <Facts report={report} />
            {report.short_comment && (
              <div className="draft-detail-section">
                <div className="section-label">Latest update</div>
                <p>{report.short_comment}</p>
              </div>
            )}
            {report.long_comment && report.long_comment !== report.short_comment && (
              <div className="draft-detail-section">
                <div className="section-label">Analysis</div>
                <p>{report.long_comment}</p>
              </div>
            )}
            <div className="injury-provenance muted">
              {formatDate(report.reported_at)
                ? `Reported ${formatDate(report.reported_at)} · `
                : ""}
              ESPN injury report, checked {formatDate(report.fetched_at)}
            </div>
          </>
        )}

        {!isLoading && !isError && !report && (
          <p className="muted">
            {payload && !payload.detail_supported
              ? "Detailed reports aren’t available for this player — the designation above comes from your league platform."
              : "No detailed report on file. The designation above comes from your league platform."}
          </p>
        )}
      </div>
    </div>,
    document.body,
  );
}
