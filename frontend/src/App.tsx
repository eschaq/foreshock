import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator } from "./components/ActivityIndicator";
import { AddVendorModal } from "./components/AddVendorModal";
import { AgentPanel } from "./components/AgentPanel";
import { DetailPanel } from "./components/DetailPanel";
import { FleetOverview } from "./components/FleetOverview";
import { RemoveVendorConfirm } from "./components/RemoveVendorConfirm";
import { RiskScale } from "./components/RiskScale";
import { SettingsGear } from "./components/SettingsGear";
import { VendorCard } from "./components/VendorCard";
import { fetchStatus, fetchVendors, triggerAgentRun } from "./lib/api";
import type { SystemStatus, VendorOverview } from "./types";

function getTriggerModeFromURL(): "live" | "seeded" {
  const params = new URLSearchParams(window.location.search);
  return params.get("mode") === "seeded" ? "seeded" : "live";
}

function writeTriggerModeToURL(mode: "live" | "seeded") {
  const params = new URLSearchParams(window.location.search);
  params.set("mode", mode);
  const newSearch = params.toString();
  const newUrl = `${window.location.pathname}${newSearch ? "?" + newSearch : ""}${window.location.hash}`;
  window.history.replaceState({}, "", newUrl);
}

function App() {
  const [vendors, setVendors] = useState<VendorOverview[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const [triggerMode, setTriggerMode] = useState<"live" | "seeded">(
    getTriggerModeFromURL()
  );

  // Toggle from the gear; keeps the ?mode= URL in sync so refresh/bookmark
  // preserves the choice and the URL channel still works.
  const handleModeChange = useCallback((mode: "live" | "seeded") => {
    setTriggerMode(mode);
    writeTriggerModeToURL(mode);
  }, []);
  // Agent panel state — replaces the previous live-pull FlowPanel as the
  // chord target. Job id comes from POST /agent/run; AgentPanel then opens
  // SSE on /agent/stream/{job_id}.
  const [agentJobId, setAgentJobId] = useState<string | null>(null);
  const [agentTriggering, setAgentTriggering] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  // Vendor management (Wave 3): add modal + remove confirm flow.
  const [showAddModal, setShowAddModal] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  // Bumped whenever the vendor scoreboard changes (initial load, live-pull
  // complete, reset). FleetOverview re-fetches on each bump; backend cache
  // is keyed by signal-counts so this is cheap when nothing has changed.
  const [fleetNonce, setFleetNonce] = useState(0);

  // Animation gate: vendor-card mount animations (sparkline draw-on + border
  // pulse) hold until the dashboard is fully ready — both the vendor scoreboard
  // AND the fleet summary card have settled. Flips once, stays true; subsequent
  // refreshes don't re-trigger the entrance animations.
  const [fleetSettled, setFleetSettled] = useState(false);
  const dashboardReady = !loading && !error && fleetSettled;
  const handleFleetSettled = useCallback(() => setFleetSettled(true), []);

  const refresh = useCallback(async () => {
    try {
      const [v, s] = await Promise.all([fetchVendors(), fetchStatus()]);
      setVendors(v);
      setStatus(s);
      setError(null);
      setFleetNonce((n) => n + 1);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  // Semi-hidden trigger: Ctrl/Cmd + Shift + L fires the unattended daily
  // agent (Pull → Clean → Promote). Same endpoint the Railway cron hits at
  // 07:00 UTC. AgentPanel then opens an SSE stream against the returned
  // job_id and renders live progress per stage.
  const triggerAgent = useCallback(async () => {
    if (agentTriggering || agentJobId) return; // ignore re-presses while running
    setAgentTriggering(true);
    setAgentError(null);
    try {
      const { job_id } = await triggerAgentRun();
      setAgentJobId(job_id);
    } catch (e) {
      setAgentError(String(e));
    } finally {
      setAgentTriggering(false);
    }
  }, [agentJobId, agentTriggering]);

  const closeAgentPanel = useCallback(() => {
    setAgentJobId(null);
    setAgentError(null);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && agentJobId) {
        closeAgentPanel();
        return;
      }
      const chord =
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        e.key.toLowerCase() === "l";
      if (!chord) return;
      e.preventDefault();
      void triggerAgent();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [agentJobId, triggerAgent, closeAgentPanel]);

  const tally: Record<string, number> = { critical: 0, warning: 0, stable: 0 };
  vendors.forEach((v) => (tally[v.state] = (tally[v.state] ?? 0) + 1));

  return (
    <div className="min-h-screen bg-base text-ink-primary">
      <header className="border-b border-rule px-6 py-4">
        <div className="max-w-7xl mx-auto space-y-3">
          <div className="flex items-baseline justify-between">
            <div>
              <img
                src="/foreshockbanner.webp"
                alt="foreshock — continuous ICT vendor risk monitoring"
                className="h-20 w-auto block select-none"
                draggable={false}
              />
              <p className="text-ink-muted text-sm mt-1">
                continuous ICT vendor risk monitoring
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="text-signal-red">{tally.critical} critical</span>
              <span className="text-signal-amber">{tally.warning} warning</span>
              <span className="text-signal-teal">{tally.stable} stable</span>
              <button
                onClick={() => setShowAddModal(true)}
                className="text-signal-blue hover:text-signal-blue/80 text-sm font-medium"
                title="Add a vendor to monitor"
              >
                + Add Vendor
              </button>
              <SettingsGear
                mode={triggerMode}
                onModeChange={handleModeChange}
                onAfterReset={refresh}
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-6 flex-wrap">
            <RiskScale />
            <ActivityIndicator status={status} triggerMode={triggerMode} />
          </div>
        </div>
      </header>

      <main className="px-6 py-6 max-w-7xl mx-auto">
        <FleetOverview nonce={fleetNonce} onSettled={handleFleetSettled} />

        {loading && <p className="text-ink-muted">loading scoreboard…</p>}
        {error && <p className="text-signal-red">error: {error}</p>}
        {!loading && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {vendors.map((v) => (
              <VendorCard
                key={v.name}
                vendor={v}
                animate={dashboardReady}
                onClick={() => setSelected(v.name)}
                onRemoveRequest={(name) => setRemoveTarget(name)}
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

      {agentJobId && (
        <AgentPanel
          jobId={agentJobId}
          onClose={closeAgentPanel}
          onComplete={refresh}
        />
      )}

      {showAddModal && (
        <AddVendorModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => {
            setShowAddModal(false);
            void refresh();
          }}
        />
      )}

      {removeTarget && (
        <RemoveVendorConfirm
          vendorName={removeTarget}
          onCancel={() => setRemoveTarget(null)}
          onRemoved={() => {
            setRemoveTarget(null);
            void refresh();
          }}
        />
      )}

      {agentError && !agentJobId && (
        <div className="fixed bottom-6 right-6 z-40 bg-surface border border-signal-red/40 rounded-lg px-4 py-3 text-sm max-w-sm">
          <p className="text-signal-red font-medium text-xs uppercase tracking-wider">
            agent trigger failed
          </p>
          <p className="text-ink-muted text-xs mt-1">{agentError}</p>
          <button
            onClick={() => setAgentError(null)}
            className="text-ink-dim hover:text-ink-primary text-[10px] mt-2"
          >
            dismiss
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
