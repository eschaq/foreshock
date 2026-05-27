import { useEffect, useRef, useState } from "react";
import { addVendor, lookupVendor } from "../lib/api";
import type { LookupMatch, VendorType } from "../types";
import { VENDOR_TYPES } from "../types";

interface Props {
  onClose: () => void;
  onAdded: () => void;
}

const DEBOUNCE_MS = 400;

export function AddVendorModal({ onClose, onAdded }: Props) {
  const [nameInput, setNameInput] = useState("");
  const [vendorType, setVendorType] = useState<VendorType | "">("");
  const [selected, setSelected] = useState<LookupMatch | null>(null);
  const [matches, setMatches] = useState<LookupMatch[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Autofocus the name field on open
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close on Esc
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  // Debounced lookup as the user types. Selecting a match clears the
  // dropdown so it doesn't reappear on every keystroke; editing the name
  // after selection clears the selection.
  function onNameChange(value: string) {
    setNameInput(value);
    if (selected && value !== selected.name) {
      setSelected(null);
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (value.trim().length < 2) {
      setMatches([]);
      setLookupLoading(false);
      return;
    }
    setLookupLoading(true);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await lookupVendor(value.trim());
        setMatches(res.matches);
      } catch {
        // Honest degrade — empty matches, user can proceed manually.
        setMatches([]);
      } finally {
        setLookupLoading(false);
      }
    }, DEBOUNCE_MS);
  }

  function selectMatch(m: LookupMatch) {
    setSelected(m);
    setNameInput(m.name);
    setMatches([]);
  }

  function clearSelection() {
    setSelected(null);
    inputRef.current?.focus();
  }

  async function handleSubmit() {
    setError(null);
    const finalName = (selected?.name ?? nameInput).trim();
    if (!finalName) {
      setError("Company name is required");
      return;
    }
    if (!vendorType) {
      setError("Vendor type is required");
      return;
    }
    setSubmitting(true);
    try {
      await addVendor({
        name: finalName,
        vendor_type: vendorType,
        cik: selected?.cik || null,
        ticker: selected?.ticker || null,
      });
      onAdded();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setSubmitting(false);
    }
  }

  const finalName = (selected?.name ?? nameInput).trim();
  const hasCik = !!selected?.cik;
  const canSubmit = !!finalName && !!vendorType && !submitting;
  const showConfirmation = !!finalName && !!vendorType;
  const showDropdown =
    !selected && matches.length > 0 && nameInput.trim().length >= 2;

  return (
    <div
      className="fixed inset-0 bg-overlay-strong z-40 flex items-start justify-center pt-24 px-4"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="bg-base border border-rule rounded-lg w-full max-w-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-rule px-5 py-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink-primary">
            Add vendor
          </h2>
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-ink-muted hover:text-ink-primary text-sm disabled:opacity-40"
          >
            close ✕
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Name input with live lookup */}
          <div className="relative">
            <label className="block text-xs uppercase tracking-wider text-ink-muted mb-1">
              Company name
            </label>
            <input
              ref={inputRef}
              type="text"
              value={nameInput}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="e.g. Salesforce"
              className="w-full bg-surface border border-rule rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-dim focus:outline-none focus:border-signal-blue/60"
              autoComplete="off"
            />
            {lookupLoading && (
              <p className="text-[10px] text-ink-dim mt-1">
                looking up SEC EDGAR…
              </p>
            )}

            {/* Live-lookup dropdown */}
            {showDropdown && (
              <div className="absolute left-0 right-0 mt-1 bg-surface border border-rule rounded shadow-xl z-10 max-h-60 overflow-y-auto">
                {matches.map((m) => (
                  <button
                    key={m.cik}
                    onClick={() => selectMatch(m)}
                    className="w-full text-left px-3 py-2 hover:bg-base border-b border-rule last:border-b-0 group"
                  >
                    <div className="text-sm text-ink-primary group-hover:text-signal-blue">
                      {m.name}
                    </div>
                    <div className="text-[10px] text-ink-muted tabular-nums mt-0.5">
                      {m.ticker ? (
                        <>
                          <span className="text-signal-blue">{m.ticker}</span>
                          {" · CIK "}
                          {m.cik}
                          {" · Public"}
                        </>
                      ) : (
                        <>CIK {m.cik}</>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {/* Selected match confirmation */}
            {selected && (
              <div className="mt-2 flex items-center gap-2 text-[11px] bg-signal-blue/10 border border-signal-blue/30 rounded px-2 py-1.5">
                <span className="text-signal-blue uppercase tracking-wider font-medium text-[9px]">
                  selected
                </span>
                <span className="text-ink-primary">
                  {selected.ticker || "—"} · CIK {selected.cik}
                </span>
                <button
                  onClick={clearSelection}
                  className="ml-auto text-ink-muted hover:text-ink-primary text-[10px]"
                >
                  change
                </button>
              </div>
            )}

            {/* No-match hint */}
            {!selected &&
              !lookupLoading &&
              nameInput.trim().length >= 2 &&
              matches.length === 0 && (
                <p className="text-[10px] text-ink-dim mt-1">
                  no SEC match — proceed manually for private companies
                </p>
              )}
          </div>

          {/* Vendor type */}
          <div>
            <label className="block text-xs uppercase tracking-wider text-ink-muted mb-1">
              Vendor type
            </label>
            <select
              value={vendorType}
              onChange={(e) => setVendorType(e.target.value as VendorType)}
              className="w-full bg-surface border border-rule rounded px-3 py-2 text-sm text-ink-primary focus:outline-none focus:border-signal-blue/60"
            >
              <option value="">— select —</option>
              {VENDOR_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Confirmation summary */}
          {showConfirmation && (
            <div className="bg-surface border border-rule rounded p-3 text-xs space-y-1">
              <div className="text-ink-muted">
                Adding:{" "}
                <span className="text-ink-primary font-medium">
                  {finalName}
                </span>
              </div>
              <div className="text-ink-muted">
                Type:{" "}
                <span className="text-ink-primary">{vendorType}</span>
              </div>
              {hasCik && selected && (
                <div className="text-ink-muted">
                  Ticker:{" "}
                  <span className="text-signal-blue tabular-nums">
                    {selected.ticker}
                  </span>
                  {" · CIK: "}
                  <span className="text-ink-primary tabular-nums">
                    {selected.cik}
                  </span>
                </div>
              )}
              <div className="text-ink-muted">
                EDGAR monitoring:{" "}
                {hasCik ? (
                  <span className="text-signal-teal">
                    active (8-K filings will be tracked)
                  </span>
                ) : (
                  <span className="text-ink-dim">
                    not available (private company / manual entry)
                  </span>
                )}
              </div>
              <div className="text-ink-dim text-[11px] pt-1">
                Monitoring starts: next agent run
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-xs text-signal-red bg-signal-red/10 border border-signal-red/30 rounded p-2 whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>

        <div className="border-t border-rule px-5 py-3 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-xs px-3 py-1.5 rounded text-ink-muted hover:text-ink-primary disabled:opacity-40"
          >
            cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="text-xs px-3 py-1.5 rounded bg-signal-blue text-white font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-signal-blue/90"
          >
            {submitting ? "adding…" : "add vendor"}
          </button>
        </div>
      </div>
    </div>
  );
}
