// Toggle switch — matches design/screen-settings.jsx's <Switch>. Rendered as
// a div (not a native checkbox) to match the prototype's `.switch` CSS, with
// role="switch" layered on for accessibility.

interface SwitchProps {
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label?: string;
}

export function Switch({ on, onChange, disabled, label }: SwitchProps) {
  return (
    <div
      className={"switch" + (on ? " on" : "")}
      role="switch"
      aria-checked={on}
      aria-label={label}
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
      onClick={() => {
        if (!disabled) onChange(!on);
      }}
      onKeyDown={(event) => {
        if (disabled) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onChange(!on);
        }
      }}
    />
  );
}
