import { useEffect, useState } from "react";
import { fetchFleetSummary } from "../lib/api";
import type { FleetSummary, RiskState } from "../types";

// Derive the fleet's worst-state from the per-state counts, so the top
// border of the Fleet Overview card visually matches the scoring bands
// in the RiskScale legend (teal=stable, amber=warning, red=critical).
// Returns null when there's no summary yet OR the fleet is empty —
// the section then falls back to a neutral `--rule` top edge.
function fleetState(summary: FleetSummary | null): RiskState | null {
  if (!summary || summary.fleet_counts.total === 0) return null;
  const c = summary.fleet_counts;
  if (c.critical > 0) return "critical";
  if (c.warning > 0) return "warning";
  return "stable";
}

// Tailwind needs class names statically discoverable, so the mapping
// lives as a literal table rather than a template string.
const TOP_BORDER: Record<RiskState, string> = {
  critical: "border-t-signal-red",
  warning: "border-t-signal-amber",
  stable: "border-t-signal-teal",
};

interface Props {
  // Bump to force a re-fetch (e.g. after a live pull lands new data).
  // The backend caches by vendor-state-hash so a re-fetch is cheap if
  // nothing changed and triggers a fresh Claude pass when it has.
  nonce?: number;
  // Called once per fetch lifecycle when the request settles (success or
  // failure). The parent uses this to know when "the dashboard is fully
  // loaded" so it can release the vendor-card mount animations.
  onSettled?: () => void;
}

/**
 * Fleet Overview card — Claude-generated 3-4 sentence portfolio briefing,
 * read from the dashboard's already-scored vendor state (summary-only
 * pattern; no raw signal rows go to Claude).
 *
 * Per DESIGN.md: not a charged moment. Static surface, no border-flash,
 * no animation. Loading state is a quiet italic muted-text indicator.
 */
export function FleetOverview({ nonce = 0, onSettled }: Props) {
  const [summary, setSummary] = useState<FleetSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchFleetSummary()
      .then((s) => {
        if (active) setSummary(s);
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          onSettled?.();
        }
      });
    return () => {
      active = false;
    };
    // onSettled deliberately omitted from deps: parent passes a stable
    // reference, and re-firing on identity changes would noise the signal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce]);

  const aiGenerated =
    summary?.generated_by && summary.generated_by !== "deterministic-fallback";
  const fallbackInUse =
    summary?.generated_by === "deterministic-fallback";

  const state = fleetState(summary);
  const topBorderClass = state ? TOP_BORDER[state] : "border-t-rule";

  return (
    <section
      className={`bg-surface border border-rule rounded-lg p-6 mb-6 ${topBorderClass}`}
    >
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-ink-muted text-[10px] uppercase tracking-wider">
          Fleet Overview
        </h2>
        {summary && (
          <span className="text-[9px] uppercase tracking-wider text-ink-dim">
            {aiGenerated
              ? "AI · synthesized from scored fleet state"
              : "deterministic fallback (AI unavailable)"}
          </span>
        )}
      </div>

      {loading && !summary && (
        <div className="text-ink-muted text-sm italic">
          synthesizing fleet view…
        </div>
      )}

      {error && !summary && (
        <p className="text-ink-dim text-sm">
          fleet summary unavailable
          <span className="text-ink-dim/70 ml-2 text-xs">({error})</span>
        </p>
      )}

      {summary && (
        <div className="space-y-2">
          <p
            className={`text-lg font-semibold leading-snug ${
              loading
                ? "text-ink-muted italic"
                : "text-ink-primary"
            }`}
          >
            {summary.headline}
          </p>
          <p
            className={`text-sm leading-relaxed ${
              loading ? "text-ink-dim italic" : "text-ink-muted"
            }`}
          >
            {summary.narrative}
          </p>
          {loading && (
            <p className="text-ink-dim text-[10px] italic">
              regenerating fleet view from latest scoreboard…
            </p>
          )}
          {fallbackInUse && summary.parse_error && (
            <p className="text-ink-dim text-[10px] italic">
              fallback reason: {summary.parse_error}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
