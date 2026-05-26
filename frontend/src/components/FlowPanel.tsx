import { useEffect, useRef, useState } from "react";
import { livePullStreamUrl } from "../lib/api";
import type { FlowEvent } from "../types";

interface Props {
  triggerNonce: number;        // bump to re-open + restream
  mode: "live" | "seeded";
  onClose: () => void;
  onComplete: () => void;       // dashboard refreshes vendors after this
}

// The judge-facing MCP-flow display. Renders ONLY whatever events arrive
// from the backend SSE stream — the honesty contract is enforced at the
// event source. Seeded mode renders fixture_read/loaded events labeled
// CACHED REPLAY; live mode renders mcp_call/mcp_result events.
export function FlowPanel({ triggerNonce, mode, onClose, onComplete }: Props) {
  const [events, setEvents] = useState<FlowEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const completedRef = useRef(false);

  useEffect(() => {
    if (triggerNonce === 0) return;
    setEvents([]);
    setStreaming(true);
    completedRef.current = false;

    const url = livePullStreamUrl(mode);
    const es = new EventSource(url);

    es.onmessage = (e) => {
      let ev: FlowEvent;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      if (ev.type === "stream_end") {
        es.close();
        setStreaming(false);
        return;
      }
      setEvents((prev) => [...prev, ev]);
      if (ev.type === "complete") {
        completedRef.current = true;
        // Defer refresh so the user sees the complete event first.
        setTimeout(() => onComplete(), 400);
      }
    };

    es.onerror = () => {
      es.close();
      setStreaming(false);
    };

    return () => es.close();
  }, [triggerNonce, mode, onComplete]);

  if (triggerNonce === 0) return null;

  return (
    <div
      className="fixed inset-0 z-40 bg-black/80 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className={`bg-base border rounded-lg w-full max-w-2xl max-h-[80vh] overflow-y-auto ${
          mode === "live"
            ? "border-signal-teal/40"
            : "border-signal-amber/40"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <FlowHeader mode={mode} streaming={streaming} />
        <div className="px-5 py-4 space-y-2 font-mono text-xs">
          {events.length === 0 && (
            <div className="text-ink-muted italic">opening stream…</div>
          )}
          {events.map((ev, i) => (
            <EventRow key={i} ev={ev} mode={mode} />
          ))}
          {streaming && (
            <div className="text-ink-dim italic animate-pulse">
              awaiting next event…
            </div>
          )}
        </div>
        <div className="px-5 py-3 border-t border-white/10 flex justify-between items-center">
          <span className="text-[10px] text-ink-dim">
            keyboard: Ctrl/Cmd + Shift + L · esc to close
          </span>
          <button
            onClick={onClose}
            className="text-xs text-ink-muted hover:text-ink-primary"
          >
            close ✕
          </button>
        </div>
      </div>
    </div>
  );
}

function FlowHeader({
  mode,
  streaming,
}: {
  mode: "live" | "seeded";
  streaming: boolean;
}) {
  const live = mode === "live";
  return (
    <div
      className={`px-5 py-4 border-b ${
        live
          ? "border-signal-teal/30 bg-signal-teal/5"
          : "border-signal-amber/30 bg-signal-amber/5"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="relative flex h-2 w-2">
          {streaming && (
            <span
              className={`absolute inline-flex h-full w-full rounded-full opacity-70 animate-ping ${
                live ? "bg-signal-teal" : "bg-signal-amber"
              }`}
            />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              live ? "bg-signal-teal" : "bg-signal-amber"
            }`}
          />
        </span>
        <h2
          className={`text-sm font-semibold tracking-wide uppercase ${
            live ? "text-signal-teal" : "text-signal-amber"
          }`}
        >
          {live
            ? "Bright Data MCP — live capture"
            : "Cached replay — network not used"}
        </h2>
      </div>
      {!live && (
        <p className="text-[10px] text-ink-muted mt-1 ml-5">
          venue-network safety net · same downstream flow as live mode · for the
          real Bright Data MCP path, switch to <code>?mode=live</code>
        </p>
      )}
      {live && (
        <p className="text-[10px] text-ink-muted mt-1 ml-5">
          real Bright Data MCP calls · streaming events from{" "}
          <code>/live-pull/stream</code>
        </p>
      )}
    </div>
  );
}

function EventRow({ ev, mode }: { ev: FlowEvent; mode: "live" | "seeded" }) {
  switch (ev.type) {
    case "start":
      return (
        <Line tone="dim">
          <span>capture_date={ev.capture_date}</span>
        </Line>
      );

    case "mcp_call":
      return (
        <Line tone="live">
          <Tag>Bright Data MCP</Tag>
          <span className="text-signal-teal">{ev.tool}</span>
          <Sep />
          <span>vendor={ev.vendor}</span>
          <Sep />
          <span className="text-ink-muted">
            query="{ev.query}"
          </span>
          <span className="text-ink-dim italic ml-2">…calling</span>
        </Line>
      );

    case "mcp_result":
      return (
        <Line tone="live">
          <Tag>Bright Data MCP</Tag>
          <span className="text-signal-teal">{ev.tool}</span>
          <Sep />
          <span>vendor={ev.vendor}</span>
          <Sep />
          <span className="text-ink-primary font-semibold">
            {ev.results_count} results
          </span>
          <Sep />
          <span className="text-ink-muted tabular-nums">
            {ev.duration_ms} ms
          </span>
          <span className="text-signal-teal ml-2">✓</span>
        </Line>
      );

    case "fixture_read":
      return (
        <Line tone="seeded">
          <Tag>cached replay</Tag>
          <span className="text-signal-amber">
            reading fixture
          </span>
          <Sep />
          <span className="text-ink-muted">{ev.fixture}</span>
          <span className="text-ink-dim italic ml-2">…loading</span>
        </Line>
      );

    case "fixture_loaded":
      return (
        <Line tone="seeded">
          <Tag>cached replay</Tag>
          <span className="text-signal-amber">fixture loaded</span>
          <Sep />
          <span className="text-ink-muted">{ev.fixture}</span>
          <Sep />
          <span className="text-ink-primary font-semibold">
            {ev.results_count} results (no network used)
          </span>
        </Line>
      );

    case "save_seed":
      return (
        <Line tone="dim">
          <span className="text-ink-muted">
            saved live response to fixture: {ev.fixture}
          </span>
        </Line>
      );

    case "rows_built":
      return (
        <Line tone="dim">
          <span className="text-ink-muted">
            built {ev.count} Type 2 rows
          </span>
          <Sep />
          <span>vendor={ev.vendor}</span>
          <Sep />
          <span className="text-ink-muted">metrics=[{ev.metrics.join(", ")}]</span>
          {ev.note && (
            <span className="text-ink-dim italic ml-2">— {ev.note}</span>
          )}
        </Line>
      );

    case "airtable_write":
      return (
        <Line tone="dim">
          <span className="text-ink-muted">
            Airtable batch_create
          </span>
          <Sep />
          {ev.status === "started" ? (
            <>
              <span>row_count={ev.row_count}</span>
              <span className="text-ink-dim italic ml-2">…writing</span>
            </>
          ) : (
            <>
              <span className="text-ink-primary font-semibold">
                {ev.rows_written} rows written
              </span>
              <span className="text-signal-teal ml-2">✓</span>
            </>
          )}
        </Line>
      );

    case "complete":
      return (
        <Line tone={mode === "live" ? "live" : "seeded"}>
          <span
            className={`font-semibold ${
              mode === "live" ? "text-signal-teal" : "text-signal-amber"
            }`}
          >
            ▸ capture complete
          </span>
          <Sep />
          <span>{ev.rows_written} rows written</span>
          <Sep />
          <span className="text-ink-muted">
            (real_vendor={ev.real_vendor_rows}, veridian_finale={ev.veridian_rows})
          </span>
          <span className="text-ink-dim italic ml-2">
            — dashboard refreshing…
          </span>
        </Line>
      );

    case "error":
      return (
        <Line tone="dim">
          <span className="text-signal-red font-semibold">✗ error</span>
          <Sep />
          {ev.stage && <span>stage={ev.stage}</span>}
          {ev.stage && <Sep />}
          <span className="text-ink-muted">{ev.message}</span>
        </Line>
      );

    default:
      return null;
  }
}

function Line({
  tone,
  children,
}: {
  tone: "live" | "seeded" | "dim";
  children: React.ReactNode;
}) {
  const marker =
    tone === "live"
      ? "text-signal-teal"
      : tone === "seeded"
      ? "text-signal-amber"
      : "text-ink-dim";
  return (
    <div className="flex items-baseline gap-2 flex-wrap leading-relaxed">
      <span className={marker}>▸</span>
      {children}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/5 text-ink-muted border border-white/10">
      {children}
    </span>
  );
}

function Sep() {
  return <span className="text-ink-dim">·</span>;
}
