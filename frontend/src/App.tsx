import { useEffect, useState } from "react";
import { DetailPanel } from "./components/DetailPanel";
import { RiskScale } from "./components/RiskScale";
import { VendorCard } from "./components/VendorCard";
import { fetchVendors } from "./lib/api";
import type { VendorOverview } from "./types";

function App() {
  const [vendors, setVendors] = useState<VendorOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    fetchVendors()
      .then(setVendors)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

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
            <span className="text-signal-red">
              {tally.critical} critical
            </span>
            <span className="text-signal-amber">
              {tally.warning} warning
            </span>
            <span className="text-signal-teal">
              {tally.stable} stable
            </span>
          </div>
        </div>
        <div className="mt-3 pt-3 border-t border-white/5">
          <RiskScale />
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
    </div>
  );
}

export default App;
