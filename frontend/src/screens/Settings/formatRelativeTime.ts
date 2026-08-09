/** Formats an ISO timestamp as a short relative string ("3 minutes ago"). */
export function formatRelativeTime(iso: string | null | undefined): string | null {
  if (!iso) return null;

  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;

  const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSec < 45) return "just now";

  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? "" : "s"} ago`;

  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour} hour${diffHour === 1 ? "" : "s"} ago`;

  const diffDay = Math.round(diffHour / 24);
  return `${diffDay} day${diffDay === 1 ? "" : "s"} ago`;
}
