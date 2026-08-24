// Build-time feature flags.
//
// DRAFT_ASSISTANT gates the /draft screen and its sidebar entry. The feature is
// complete and tested (backend, board import, and API stay live regardless — only
// the UI surface is gated); it's off between drafts so the nav isn't cluttered by a
// screen that's useful a few nights a year. Flip to `true` to bring it back.
export const DRAFT_ASSISTANT = false;
