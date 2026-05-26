import type { SystemStatus } from "../types";

interface Props {
  status: SystemStatus | null;
  triggerMode: "live" | "seeded";
}

// Subtle always-on element reinforcing the "continuous monitoring" claim.
// Dot pulses softly. Includes the trigger-mode hint so an operator can
// glance up before pressing the chord and know which path will run.
export function ActivityIndicator({ status, triggerMode }: Props) {
  const lastPull = status?.last_capture ?? "—";
  const total = status?.signal_count_total ?? 0;
  return (
    <div className="flex items-center gap-2 text-[10px] text-ink-muted">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full rounded-full bg-signal-teal opacity-60 animate-ping" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-signal-teal" />
      </span>
      <span>monitoring active</span>
      <span className="text-ink-dim">·</span>
      <span>
        last pull <span className="text-ink-primary font-mono">{lastPull}</span>
      </span>
      <span className="text-ink-dim">·</span>
      <span>
        {total} signals
      </span>
      <span className="text-ink-dim">·</span>
      <span
        className={
          triggerMode === "live"
            ? "text-signal-teal italic"
            : "text-signal-amber italic"
        }
        title={
          triggerMode === "live"
            ? "next pull will hit Bright Data MCP"
            : "next pull will use cached fixture (no network)"
        }
      >
        trigger: {triggerMode}
      </span>
    </div>
  );
}
