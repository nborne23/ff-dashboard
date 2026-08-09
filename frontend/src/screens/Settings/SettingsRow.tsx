// Row primitive for .settings-group — matches design/screen-settings.jsx's
// <SettingsRow>. Unlike the prototype, we don't need a `last` prop: the
// `.settings-group .row:last-child` rule in global.css already drops the
// border on the final row regardless of what precedes it.

import type { ReactNode } from "react";

import { Skeleton } from "../../components/primitives";

interface SettingsRowProps {
  label: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
}

export function SettingsRow({ label, sub, right }: SettingsRowProps) {
  return (
    <div className="row">
      <div className="label">
        <div>{label}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}

/** Placeholder row shown while a settings-group's data is loading. */
export function SkeletonRow() {
  return (
    <div className="row" data-testid="settings-row-skeleton">
      <div className="label">
        <Skeleton width="60%" height={14} />
      </div>
    </div>
  );
}
