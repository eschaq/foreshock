import { useEffect, useRef, useState } from "react";

interface Props {
  mode: "live" | "seeded";
  onModeChange: (mode: "live" | "seeded") => void;
  onAfterReset: () => void;  // dashboard refresh after a reset
}

// Operator-facing settings dropdown. Same mode that `?mode=` URL param drives —
// the gear just makes it clickable. Honesty rule (step 7.5) is preserved
// because mode flows through the same channel as before: only the SOURCE of
// the mode value moves; the FlowPanel still renders whatever events arrive.
export function SettingsGear({ mode, onModeChange, onAfterReset }: Props) {
  const [open, setOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetFeedback, setResetFeedback] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click or Esc.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleReset() {
    setResetting(true);
    setResetFeedback(null);
    try {
      const res = await fetch("/api/live-pull/reset", { method: "POST" });
      const data = (await res.json()) as { deleted: number };
      setResetFeedback(`deleted ${data.deleted} row${data.deleted === 1 ? "" : "s"}`);
      onAfterReset();
    } catch (e) {
      setResetFeedback(`reset failed: ${String(e)}`);
    } finally {
      setResetting(false);
      setTimeout(() => setResetFeedback(null), 4000);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Settings"
        className={`w-7 h-7 flex items-center justify-center rounded text-ink-muted hover:text-ink-primary hover:bg-white/5 transition-colors ${
          open ? "bg-white/5 text-ink-primary" : ""
        }`}
      >
        <GearIcon />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 bg-surface border border-white/10 rounded-lg shadow-xl z-50">
          <div className="px-4 py-3 border-b border-white/5">
            <p className="text-[10px] uppercase tracking-wider text-ink-dim">
              Settings
            </p>
          </div>

          {/* Trigger mode toggle */}
          <div className="px-4 py-3 border-b border-white/5">
            <p className="text-[10px] uppercase tracking-wider text-ink-dim mb-2">
              Trigger mode
            </p>
            <div className="grid grid-cols-2 gap-1">
              <ModeButton
                label="live"
                active={mode === "live"}
                onClick={() => onModeChange("live")}
                activeClasses="bg-signal-teal/15 border-signal-teal/50 text-signal-teal"
              />
              <ModeButton
                label="seeded"
                active={mode === "seeded"}
                onClick={() => onModeChange("seeded")}
                activeClasses="bg-signal-amber/15 border-signal-amber/50 text-signal-amber"
              />
            </div>
            <ul className="mt-2 space-y-1 text-[10px] text-ink-muted leading-snug">
              <li>
                <span className="text-signal-teal">live</span> — real Bright
                Data MCP call (search_engine)
              </li>
              <li>
                <span className="text-signal-amber">seeded</span> — cached
                replay; no network
              </li>
            </ul>
          </div>

          {/* Shortcut reminder */}
          <div className="px-4 py-3 border-b border-white/5">
            <p className="text-[10px] uppercase tracking-wider text-ink-dim mb-2">
              Shortcut
            </p>
            <ul className="text-xs space-y-1">
              <li className="flex justify-between items-center">
                <span className="text-ink-muted">trigger live pull</span>
                <Kbd>Ctrl/Cmd + Shift + L</Kbd>
              </li>
              <li className="flex justify-between items-center">
                <span className="text-ink-muted">close panels</span>
                <Kbd>Esc</Kbd>
              </li>
            </ul>
          </div>

          {/* Reset */}
          <div className="px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-dim mb-2">
              Rehearsal
            </p>
            <button
              onClick={handleReset}
              disabled={resetting}
              className="w-full text-left text-xs px-3 py-2 rounded border border-white/10 hover:border-white/20 hover:bg-white/5 disabled:opacity-50 transition-colors"
            >
              {resetting ? "resetting…" : "reset live-pull rows"}
            </button>
            <p className="text-[10px] text-ink-dim mt-1.5">
              deletes rows tagged{" "}
              <code className="text-ink-muted">live-pull-beat:</code>
            </p>
            {resetFeedback && (
              <p className="text-[10px] text-signal-teal mt-1.5">
                {resetFeedback}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ModeButton({
  label,
  active,
  onClick,
  activeClasses,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  activeClasses: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 rounded text-xs uppercase tracking-wider font-medium border transition-colors ${
        active
          ? activeClasses
          : "bg-transparent border-white/10 text-ink-muted hover:text-ink-primary hover:border-white/20"
      }`}
    >
      {label}
      {active && <span className="ml-1 text-[10px]">✓</span>}
    </button>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <code className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-ink-muted font-mono">
      {children}
    </code>
  );
}

function GearIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
