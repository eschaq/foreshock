import { useMemo } from "react";
import { isEdgarMonitored } from "../lib/edgar";
import type { RiskState, VendorOverview } from "../types";

interface Props {
  vendors: VendorOverview[];
  onSelect: (name: string) => void;
}

const STATE_BG: Record<RiskState, string> = {
  stable: "bg-signal-teal/85",
  warning: "bg-signal-amber/85",
  critical: "bg-signal-red/85",
};

/**
 * Concentration risk view (DORA-relevant).
 *
 * Stacks every vendor on a shared time axis so the eye can scan
 * vertically and see whether multiple vendors are deteriorating in the
 * same window — the actual concentration signal. Per-vendor state at
 * each axis date is derived by carry-forward from the trajectory data
 * already returned by /vendors (no new endpoint).
 */
export function ConcentrationRisk({ vendors, onSelect }: Props) {
  // Shared time axis = union of all capture dates across all vendors.
  // Sorted ascending so left-to-right = oldest-to-newest.
  const axisDates = useMemo(() => {
    const set = new Set<string>();
    for (const v of vendors) {
      for (const p of v.trajectory) set.add(p.date);
    }
    return Array.from(set).sort();
  }, [vendors]);

  // Carry-forward: at a given axis date, the vendor's state is whatever
  // it was at their latest trajectory point on-or-before that date. If
  // they have no point yet (new vendor, axis date predates their first
  // capture), return null and the cell renders as "no data" muted.
  function stateAt(vendor: VendorOverview, date: string): RiskState | null {
    let last: RiskState | null = null;
    for (const p of vendor.trajectory) {
      if (p.date <= date) last = p.state;
      else break;
    }
    return last;
  }

  if (vendors.length === 0 || axisDates.length === 0) return null;

  const startDate = axisDates[0];
  const endDate = axisDates[axisDates.length - 1];

  return (
    <section className="bg-surface border border-rule rounded-lg px-5 pt-3 pb-3 mb-6">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-ink-muted text-[10px] uppercase tracking-wider">
          Concentration Risk
        </h2>
        <span className="text-[9px] uppercase tracking-wider text-ink-muted">
          vendor risk states over monitoring window
        </span>
      </div>

      <div className="space-y-px">
        {vendors.map((v) => {
          const sec = isEdgarMonitored(v.name, v.is_demo);
          return (
            <button
              key={v.name}
              onClick={() => onSelect(v.name)}
              className="w-full flex items-center gap-3 hover:bg-base/40 rounded px-1 py-0.5 transition-colors text-left focus:outline-none focus:bg-base/40"
              title={`Open ${v.name} detail`}
            >
              <div className="w-36 flex items-center gap-1.5 min-w-0">
                <span className="text-xs text-ink-primary truncate">
                  {v.name}
                </span>
                {sec && (
                  <span className="shrink-0 text-[8px] uppercase tracking-wider bg-signal-blue text-white px-1 py-px rounded leading-none">
                    sec
                  </span>
                )}
                {v.is_demo && (
                  <span className="shrink-0 text-[8px] uppercase tracking-wider text-ink-dim border border-ink-dim/30 px-1 py-px rounded leading-none">
                    demo
                  </span>
                )}
              </div>

              <div className="flex-1 flex h-3 gap-px rounded overflow-hidden">
                {axisDates.map((d) => {
                  const s = stateAt(v, d);
                  const color = s ? STATE_BG[s] : "bg-rule/40";
                  const label = s ? `${d}: ${s}` : `${d}: no data yet`;
                  return (
                    <div
                      key={d}
                      className={`flex-1 ${color}`}
                      title={label}
                    />
                  );
                })}
              </div>

              <div className="w-12 text-right font-mono tabular-nums text-xs text-ink-primary">
                {v.score.toFixed(1)}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex items-center justify-between text-[9px] text-ink-dim font-mono tabular-nums">
        <span>{startDate}</span>
        <span className="text-ink-dim/70">
          {axisDates.length} capture date{axisDates.length === 1 ? "" : "s"}
        </span>
        <span>{endDate}</span>
      </div>
    </section>
  );
}
