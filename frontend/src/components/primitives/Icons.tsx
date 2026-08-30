// GridIron — SVG icons, ported 1:1 from design/primitives.jsx (SF-Symbol-feel,
// line weight ~1.75).

import type { ReactNode } from "react";

export interface IconProps {
  size?: number;
  stroke?: string;
  fill?: string;
}

function Icon({
  children,
  size = 18,
  stroke = "currentColor",
  fill = "none",
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke={stroke}
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function IconMenu(p: IconProps) {
  return (
    <Icon {...p}>
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </Icon>
  );
}

export function IconDashboard(p: IconProps) {
  return (
    <Icon {...p}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Icon>
  );
}

export function IconTeams(p: IconProps) {
  return (
    <Icon {...p}>
      <circle cx="9" cy="8" r="3.2" />
      <circle cx="17" cy="9" r="2.4" />
      <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" />
      <path d="M14 19c.4-2.4 2-4 4-4 1.6 0 2.8.7 3.5 2" />
    </Icon>
  );
}

export function IconMatchups(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M5 4h4l1.5 5L8 13l2 7H5" />
      <path d="M19 4h-4l-1.5 5L16 13l-2 7h5" />
    </Icon>
  );
}

export function IconSeason(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M3 20V8m5 12V4m5 16v-9m5 9V12" />
    </Icon>
  );
}

export function IconSettings(p: IconProps) {
  return (
    <Icon {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1A1.7 1.7 0 0 0 20.9 10H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </Icon>
  );
}

export function IconChevR(p: IconProps) {
  return (
    <Icon {...p}>
      <polyline points="9 6 15 12 9 18" />
    </Icon>
  );
}

export function IconArrowL(p: IconProps) {
  return (
    <Icon {...p}>
      <polyline points="15 6 9 12 15 18" />
    </Icon>
  );
}

export function IconArrowR(p: IconProps) {
  return (
    <Icon {...p}>
      <polyline points="9 6 15 12 9 18" />
    </Icon>
  );
}

export function IconRefresh(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <polyline points="21 4 21 9 16 9" />
    </Icon>
  );
}

export function IconUp(p: IconProps) {
  return (
    <Icon {...p}>
      <polyline points="6 14 12 8 18 14" />
    </Icon>
  );
}

export interface IconFootballProps {
  size?: number;
  color?: string;
}

export function IconFootball({ size = 18, color = "#FF2D55" }: IconFootballProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M4 12c0-4.4 3.6-8 8-8s8 3.6 8 8-3.6 8-8 8-8-3.6-8-8z"
        stroke={color}
        strokeWidth="1.75"
        transform="rotate(-30 12 12)"
      />
      <path
        d="M9 12h6M11 9.5v5M13 9.5v5"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        transform="rotate(-30 12 12)"
      />
    </svg>
  );
}

export function IconCalendar(p: IconProps) {
  return (
    <Icon {...p}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </Icon>
  );
}

export function IconShield(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6l8-3z" />
    </Icon>
  );
}

export function IconBolt(p: IconProps) {
  return (
    <Icon {...p} fill="currentColor" stroke="none">
      <polygon points="13 2 4 14 11 14 9 22 20 10 13 10 15 2" />
    </Icon>
  );
}

export function IconStar(p: IconProps) {
  return (
    <Icon {...p} fill="currentColor" stroke="none">
      <polygon points="12 2 15 9 22 10 17 15 18 22 12 19 6 22 7 15 2 10 9 9" />
    </Icon>
  );
}

export function IconFlame(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M12 3c1 3 4 4 4 8a4 4 0 1 1-8 0c0-2 1-3 1-5 1 1 3 1 3-3z" />
    </Icon>
  );
}

export function IconCheck(p: IconProps) {
  return (
    <Icon {...p}>
      <polyline points="5 12 10 17 19 7" />
    </Icon>
  );
}

export function IconX(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icon>
  );
}

export function IconPlus(p: IconProps) {
  return (
    <Icon {...p}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function IconLock(p: IconProps) {
  return (
    <Icon {...p}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V7a4 4 0 1 1 8 0v4" />
    </Icon>
  );
}

/** Error state icon (components/shared/ErrorCard.tsx, task 10.2) — same SF-Symbol-feel
 * line weight as the rest of Icons.tsx, not ported from design (the static prototype
 * has no error states to draw one from). */
export function IconAlertCircle(p: IconProps) {
  return (
    <Icon {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" />
      <path d="M12 16.2v.01" />
    </Icon>
  );
}
