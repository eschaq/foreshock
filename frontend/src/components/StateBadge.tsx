import type { RiskState } from "../types";

const STYLE: Record<RiskState, string> = {
  stable:
    "bg-signal-teal/10 text-signal-teal border-signal-teal/40",
  warning:
    "bg-signal-amber/10 text-signal-amber border-signal-amber/40",
  critical:
    "bg-signal-red/15 text-signal-red border-signal-red/50",
};

export function StateBadge({ state }: { state: RiskState }) {
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${STYLE[state]}`}
    >
      {state}
    </span>
  );
}
