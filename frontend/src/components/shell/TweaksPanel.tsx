// Simplified port of design/tweaks-panel.jsx + design/app.jsx's tweaks
// wiring. The prototype's drag-to-reposition and design-tool "host protocol"
// (postMessage handshake) are intentionally dropped — this only needs to
// read/write the six persisted tweaks in the real app.

import { useState } from "react";

import { useUiStore } from "../../stores/ui";
import { IconSettings, IconX } from "../primitives";
import "./TweaksPanel.css";

function TweakSlider({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="twk-row">
      <div className="twk-lbl">
        <span>{label}</span>
        <span className="twk-val">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        className="twk-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function TweaksPanel() {
  const [open, setOpen] = useState(false);
  const tweaks = useUiStore((s) => s.tweaks);
  const setTweak = useUiStore((s) => s.setTweak);

  if (!open) {
    return (
      <button
        type="button"
        className="twk-gear"
        aria-label="Open tweaks"
        onClick={() => setOpen(true)}
      >
        <IconSettings size={16} />
      </button>
    );
  }

  return (
    <div className="twk-panel">
      <div className="twk-hd">
        <b>Tweaks</b>
        <button
          type="button"
          className="twk-x"
          aria-label="Close tweaks"
          onClick={() => setOpen(false)}
        >
          <IconX size={12} />
        </button>
      </div>
      <div className="twk-body">
        <div className="twk-sect">Layout</div>
        <TweakSlider
          label="Sidebar width"
          value={tweaks.sidebarWidth}
          min={200}
          max={280}
          step={4}
          unit="px"
          onChange={(v) => setTweak("sidebarWidth", v)}
        />
        <TweakSlider
          label="Roster row height"
          value={tweaks.rowHeight}
          min={48}
          max={72}
          step={2}
          unit="px"
          onChange={(v) => setTweak("rowHeight", v)}
        />
        <div className="twk-sect">Visuals</div>
        <TweakSlider
          label="Sparkline thickness"
          value={tweaks.sparkThickness}
          min={1}
          max={3}
          step={0.25}
          unit="px"
          onChange={(v) => setTweak("sparkThickness", v)}
        />
        <TweakSlider
          label="Aurora intensity"
          value={tweaks.auroraIntensity}
          min={0}
          max={0.4}
          step={0.02}
          onChange={(v) => setTweak("auroraIntensity", v)}
        />
      </div>
    </div>
  );
}
