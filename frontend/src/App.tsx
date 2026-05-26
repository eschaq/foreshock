import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator } from "./components/ActivityIndicator";
import { DetailPanel } from "./components/DetailPanel";
import { FlowPanel } from "./components/FlowPanel";
import { RiskScale } from "./components/RiskScale";
import { VendorCard } from "./components/VendorCard";
import { fetchStatus, fetchVendors } from "./lib/api";
import type { SystemStatus, VendorOverview } from "./types";

function getTriggerModeFromURL(): "live" | "seeded" {
  const params = new URLSearchParams(window.location.search);
  return params.get("mode") === "seeded" ? "seeded" : "live";
}

function App() {
  const [vendors, setVendors] = useState<VendorOverview[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const [triggerMode] = useState<"live" | "seeded">(getTriggerModeFromURL());
  const [flowNonce, setFlowNonce] = useState(0);
  const [flowOpen, setFlowOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [v, s] = await Promise.all([fetchVendors(), fetchStatus()]);
      setVendors(v);
      setStatus(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  // Semi-hidden trigger: Ctrl/Cmd + Shift + L fires the live pull in the
  // mode currently set by the URL (?mode=live|seeded, default live).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Esc closes the flow panel
      if (e.key === "Escape" && flowOpen) {
        setFlowOpen(false);
        return;
      }
      const chord =
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        e.key.toLowerCase() === "l";
      if (!chord) return;
      e.preventDefault();
      setFlowOpen(true);
      setFlowNonce((n) => n + 1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flowOpen]);

  const tally: Record<string, number> = { critical: 0, warning: 0, stable: 0 };
  vendors.forEach((v) => (tally[v.state] = (tally[v.state] ?? 0) + 1));

  return (
    <div className="min-h-screen bg-base text-ink-primary">
      <header className="border-b border-white/10 px-6 py-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">foreshock</h1>
            <p className="text-ink-muted text-xs">
              continuous ICT vendor risk monitoring
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="text-signal-red">{tally.critical} critical</span>
            <span className="text-signal-amber">{tally.warning} warning</span>
            <span className="text-signal-teal">{tally.stable} stable</span>
          </div>
        </div>
        <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between gap-6 flex-wrap">
          <RiskScale />
          <ActivityIndicator status={status} triggerMode={triggerMode} />
        </div>
      </header>

      <main className="px-6 py-6 max-w-7xl mx-auto">
        {loading && <p className="text-ink-muted">loading scoreboard…</p>}
        {error && <p className="text-signal-red">error: {error}</p>}
        {!loading && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {vendors.map((v) => (
              <VendorCard
                key={v.name}
                vendor={v}
                onClick={() => setSelected(v.name)}
              />
            ))}
          </div>
        )}
      </main>

      {selected && (
        <DetailPanel
          vendorName={selected}
          onClose={() => setSelected(null)}
        />
      )}

      {flowOpen && (
        <FlowPanel
          triggerNonce={flowNonce}
          mode={triggerMode}
          onClose={() => setFlowOpen(false)}
          onComplete={refresh}
        />
      )}
    </div>
  );
}

export default App;
