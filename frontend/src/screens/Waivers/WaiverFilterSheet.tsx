// The Waivers filter sheet — Yahoo's "Filters" sheet, in this app's own dialog shape.
//
// Reuses the `.draft-detail-overlay` / `.draft-detail-panel` pair the other dialogs use
// (a bottom sheet on a phone, a centered card from 768px), rendered into <body> for the
// reason PlayerHealthPanel gives: `position: fixed` resolves against any transformed
// ancestor, and a portal removes that whole class of failure.
//
// Choices are a draft until "Apply Filters", as in Yahoo: flicking through options must
// not refetch the list behind the sheet on every tap. "Reset" resets the draft only.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import "../../styles/waivers.css";

import { IconCheck, IconX } from "../../components/primitives";
import { Switch } from "../Settings/Switch";
import {
  DEFAULT_WAIVER_FILTERS,
  SORT_OPTIONS,
  sheetFiltersOf,
  statusOptionId,
  statusOptions,
  type SheetFilters,
} from "./filters";

export interface WaiverFilterSheetProps {
  filters: SheetFilters;
  /** Remaining game days this week, `YYYY-MM-DD`, from the waivers payload. */
  gameDays: string[];
  onApply: (filters: SheetFilters) => void;
  onClose: () => void;
}

function OptionRow({
  selected,
  onSelect,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={"waiver-sheet-option" + (selected ? " selected" : "")}
      onClick={onSelect}
    >
      <span className="waiver-sheet-option-label">{children}</span>
      {selected && (
        <span className="waiver-sheet-check" aria-hidden="true">
          <IconCheck size={20} />
        </span>
      )}
    </button>
  );
}

export function WaiverFilterSheet({ filters, gameDays, onApply, onClose }: WaiverFilterSheetProps) {
  const [draft, setDraft] = useState<SheetFilters>(filters);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lock the page behind the sheet, as PlayerHealthPanel does — on iOS an unlocked body
  // scrolls under a bottom sheet and reads as the sheet sliding up the page.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  const options = statusOptions(gameDays);
  // A remembered game day that has since played out has no row; show the plain
  // "All Available" as chosen rather than nothing at all.
  const draftId = statusOptionId(draft);
  const selectedStatus = options.some((o) => o.id === draftId) ? draftId : draft.status;

  return createPortal(
    <div
      className="draft-detail-overlay"
      onClick={onClose}
      data-testid="waiver-filter-overlay"
      role="presentation"
    >
      <div
        className="draft-detail-panel card waiver-sheet"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="waiver-sheet-title"
        data-testid="waiver-filter-sheet"
      >
        <div className="waiver-sheet-grabber" aria-hidden="true" />
        <header className="waiver-sheet-header">
          <h2 id="waiver-sheet-title" className="waiver-sheet-title">
            Filters
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="waiver-sheet-close"
            aria-label="Close filters"
            onClick={onClose}
          >
            <IconX size={20} />
          </button>
        </header>

        <div className="waiver-sheet-body">
          <div className="waiver-sheet-toggle">
            <span>Show My Team</span>
            <Switch
              on={draft.showMine}
              onChange={(showMine) => setDraft({ ...draft, showMine })}
              label="Show My Team"
            />
          </div>

          <section>
            <h3 className="waiver-sheet-section" id="waiver-sheet-status">
              Status
            </h3>
            <div role="radiogroup" aria-labelledby="waiver-sheet-status">
              {options.map((option) => (
                <OptionRow
                  key={option.id}
                  selected={selectedStatus === option.id}
                  onSelect={() =>
                    setDraft({ ...draft, status: option.status, gameDay: option.gameDay })
                  }
                >
                  {option.label}
                </OptionRow>
              ))}
            </div>
          </section>

          <section>
            <h3 className="waiver-sheet-section" id="waiver-sheet-sort">
              Sort By
            </h3>
            <div role="radiogroup" aria-labelledby="waiver-sheet-sort">
              {SORT_OPTIONS.map((option) => (
                <OptionRow
                  key={option.id}
                  selected={draft.sort === option.id}
                  onSelect={() => setDraft({ ...draft, sort: option.id })}
                >
                  {option.label}
                  <span className="waiver-sheet-option-detail"> · {option.detail}</span>
                </OptionRow>
              ))}
            </div>
          </section>
        </div>

        <footer className="waiver-sheet-footer">
          <button
            type="button"
            className="btn waiver-sheet-reset"
            onClick={() => setDraft(sheetFiltersOf(DEFAULT_WAIVER_FILTERS))}
          >
            Reset
          </button>
          <button
            type="button"
            className="btn primary waiver-sheet-apply"
            onClick={() => onApply(draft)}
          >
            Apply Filters
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
