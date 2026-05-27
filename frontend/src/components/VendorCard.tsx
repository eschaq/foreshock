import { isEdgarMonitored } from "../lib/edgar";
import type { VendorOverview } from "../types";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

interface Props {
  vendor: VendorOverview;
  onClick: () => void;
  // Called when the hover X is clicked (user-added vendors only).
  // Parent opens a confirm modal — this prop doesn't itself remove.
  onRemoveRequest?: (name: string) => void;
  // When false, the border-pulse class is not applied (no animation).
  // Flips to true once the parent decides the dashboard is fully ready
  // (vendors + fleet summary both settled). CSS animations fire when the
  // class is first added — that's our one-shot guarantee. Default true so
  // any future call-site that doesn't gate behaves as the original spec.
  animate?: boolean;
}

// `prefers-reduced-motion` check (synchronous DOM read at render time).
// Same guard the Sparkline uses — both effects honor the OS-level
// "I don't want motion" signal. SSR-safe via the typeof window check.
function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function VendorCard({
  vendor,
  onClick,
  onRemoveRequest,
  animate = true,
}: Props) {
  // One-shot border pulse for non-stable vendors only, fired when the
  // parent flips `animate` true (dashboard fully loaded). The keyframes
  // (defined in tailwind.config.js) animate border-color + box-shadow
  // glow from the state hue to the resting rule color over 1500ms
  // ease-out-quart, forwards-filled so the end state persists. Timed to
  // overlap the Sparkline's 1200ms draw-on and complete ~300ms after.
  //
  // STABLE cards: pulseClass is empty string — no animation, resting
  // border stays at `border-rule` from mount onward. Hover-emphasis still
  // works. Before `animate` flips true, the class is also absent — the
  // pulse waits for the gate.
  const pulseClass = (() => {
    if (!animate) return "";
    if (vendor.state === "stable") return "";
    if (prefersReducedMotion()) return "";
    if (vendor.state === "critical") return "animate-card-pulse-critical";
    if (vendor.state === "warning") return "animate-card-pulse-warning";
    return "";
  })();

  // Card is a div (not a button) so the remove-X can be a real button
  // inside it without nested-interactive a11y issues. Enter/Space still
  // open the detail panel; focus ring matches the hover border.
  function handleKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  }
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKey}
      className={`group relative text-left bg-surface border border-rule rounded-lg p-4 hover:border-ink-primary/15 focus:outline-none focus:border-signal-blue/50 transition-colors w-full cursor-pointer ${pulseClass}`}
    >
      {vendor.is_removable && onRemoveRequest && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemoveRequest(vendor.name);
          }}
          onKeyDown={(e) => e.stopPropagation()}
          aria-label={`Remove ${vendor.name}`}
          title={`Remove ${vendor.name}`}
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity text-ink-dim hover:text-signal-red text-sm w-5 h-5 flex items-center justify-center rounded hover:bg-base"
        >
          ✕
        </button>
      )}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-ink-primary font-semibold text-base">
              {vendor.name}
            </h3>
            {vendor.is_demo && (
              <span className="text-[9px] uppercase tracking-wider text-ink-dim border border-ink-dim/30 px-1.5 py-0.5 rounded">
                demo
              </span>
            )}
            {isEdgarMonitored(vendor.name, vendor.is_demo) && (
              <span
                className="text-[9px] uppercase tracking-wider bg-signal-blue text-white px-1.5 py-0.5 rounded"
                title="SEC EDGAR monitoring active — 8-K filings tracked"
              >
                sec
              </span>
            )}
          </div>
          <p className="text-ink-muted text-xs mt-0.5">{vendor.type}</p>
        </div>
        <StateBadge state={vendor.state} />
      </div>

      <div className="mt-4 flex items-end gap-4">
        <div className="text-ink-primary text-3xl font-bold tabular-nums leading-none">
          {vendor.score.toFixed(1)}
        </div>
        <div className="flex-1 flex justify-end">
          <Sparkline points={vendor.trajectory} animate={animate} />
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
        <span>
          convergence:{" "}
          <span className="text-ink-primary">{vendor.convergence_count}</span>
        </span>
        <span>
          {vendor.signal_count} signals · latest{" "}
          {vendor.latest_capture ?? "—"}
        </span>
      </div>
    </div>
  );
}
