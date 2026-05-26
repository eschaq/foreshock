import type { VendorOverview } from "../types";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

interface Props {
  vendor: VendorOverview;
  onClick: () => void;
}

export function VendorCard({ vendor, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="text-left bg-surface border border-white/5 rounded-lg p-4 hover:border-white/15 transition-colors w-full"
    >
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
          </div>
          <p className="text-ink-muted text-xs mt-0.5">{vendor.type}</p>
        </div>
        <StateBadge state={vendor.state} />
      </div>

      <div className="mt-4 flex items-end gap-4">
        <div>
          <div className="text-ink-primary text-3xl font-mono tabular-nums leading-none">
            {vendor.score.toFixed(1)}
          </div>
          <div className="text-ink-dim text-[10px] uppercase tracking-wider mt-1">
            risk score
          </div>
        </div>
        <div className="flex-1 flex justify-end">
          <Sparkline points={vendor.trajectory} />
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
    </button>
  );
}
