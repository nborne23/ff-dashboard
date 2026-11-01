// "Open in ESPN" / "Open in Yahoo": hands the team on screen off to its platform's app.
//
// A plain link rather than a button with a click handler, so long-press, copy-link and
// open-in-new-tab all behave as they do for any link. See `sourceAppUrl.ts` for why
// the URL is a universal link and not a custom scheme.

import { sourceAppLink } from "./sourceAppUrl";
import "../../styles/source-link.css";

interface SourceAppLinkButtonProps {
  teamId: string;
  /** Appended to the accessible name, after the visible "Open in …" (label-in-name). */
  teamName?: string;
}

export function SourceAppLinkButton({ teamId, teamName }: SourceAppLinkButtonProps) {
  const link = sourceAppLink(teamId);
  if (!link) return null;

  return (
    <a
      className="source-link"
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Open in ${link.label}` + (teamName ? `: ${teamName}` : "")}
      data-testid="source-app-link"
    >
      <span className="source-link-text">
        <span className="source-link-verb">Open in </span>
        {link.label}
      </span>
      <IconArrowUpRight />
    </a>
  );
}

/** SF Symbols' `arrow.up.right` in Icons.tsx's 24-box style, a touch heavier (2) so it
 *  holds up at 14px. */
function IconArrowUpRight() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7 17 17 7M8 7h9v9" />
    </svg>
  );
}
