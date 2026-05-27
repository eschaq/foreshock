import React, { useEffect, useRef, useState } from "react";
import { agentStreamUrl } from "../lib/api";
import type { AgentEvent, AgentSummary } from "../types";

interface Props {
  jobId: string;
  onClose: () => void;
  onComplete: () => void;
}

type Phase = "idle" | "running" | "done";

interface PullEntry {
  vendor: string;
  tool: string;
  cls?: string;
  query?: string;
  status: "firing" | "done" | "failed";
  results?: number;
  durationMs?: number;
  path?: string;
  error?: string;
}

interface CleanEntry {
  vendor: string;
  metric: string;
  verdict: "kept" | "rejected";
  reason: string;
  title?: string;
}

interface PromoteEntry {
  vendor: string;
  status: "done" | "failed";
  rowsWritten?: number;
  rowsAttempted?: number;
  error?: string;
}

interface PullSummary {
  rowsPulled: number;
  failures: number;
  fallbackCalls: number;
}
interface CleanSummary {
  kept: number;
  rejected: number;
  candidates: number;
}
interface PromoteSummary {
  rowsWritten: number;
  failures: number;
}

/**
 * Agent panel — 3-stage pipeline UI for the unattended daily run.
 *
 * Mounts when the operator triggers POST /agent/run (chord or button).
 * Opens an EventSource on /agent/stream/{job_id} and routes incoming
 * events to the appropriate stage column. Each stage has its own live
 * log feed (Sometype Mono — the structurally-correct place for mono).
 *
 * Pipeline:
 *   Pull     → MCP calls per vendor (search_engine + fallback)
 *   Clean    → AI validator on event candidates
 *   Promote  → Airtable Type 2 append, grouped by vendor
 *   Complete → final summary card at the bottom
 */
export function AgentPanel({ jobId, onClose, onComplete }: Props) {
  const [pullPhase, setPullPhase] = useState<Phase>("idle");
  const [cleanPhase, setCleanPhase] = useState<Phase>("idle");
  const [promotePhase, setPromotePhase] = useState<Phase>("idle");

  const [pullEntries, setPullEntries] = useState<PullEntry[]>([]);
  const [cleanEntries, setCleanEntries] = useState<CleanEntry[]>([]);
  const [promoteEntries, setPromoteEntries] = useState<PromoteEntry[]>([]);

  const [pullSummary, setPullSummary] = useState<PullSummary | null>(null);
  const [cleanSummary, setCleanSummary] = useState<CleanSummary | null>(null);
  const [promoteSummary, setPromoteSummary] = useState<PromoteSummary | null>(
    null
  );

  const [summary, setSummary] = useState<AgentSummary | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const completedRef = useRef(false);

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(agentStreamUrl(jobId));

    es.onmessage = (e) => {
      let ev: AgentEvent;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      handleEvent(ev);
    };

    es.onerror = () => {
      // Streams close cleanly via the stream_end / type:timeout sentinel;
      // an onerror fire usually means the server closed after sending all
      // events. Don't surface an error unless we never completed.
      if (!completedRef.current) {
        setStreamError("stream closed before completion");
      }
      es.close();
    };

    function handleEvent(ev: AgentEvent) {
      if ("type" in ev) {
        if (ev.type === "stream_end" || ev.type === "timeout") {
          completedRef.current = true;
          es.close();
          // Best-effort: let parent know vendor data may have changed.
          onComplete();
        }
        return;
      }

      switch (ev.step) {
        case "pull": {
          if ("phase" in ev) {
            if (ev.phase === "start") {
              setPullPhase("running");
            } else if (ev.phase === "done") {
              setPullPhase("done");
              setCleanPhase("running"); // bridge: next step about to start
              setPullSummary({
                rowsPulled: ev.rows_pulled,
                failures: ev.failures,
                fallbackCalls: ev.fallback_calls,
              });
            }
          } else if ("status" in ev) {
            // Per-call event. Update-or-append: keep the row keyed by
            // (vendor, class) so firing → done collapses into one row.
            const key = `${ev.vendor}::${ev.class ?? ev.tool}`;
            setPullEntries((prev) => {
              const idx = prev.findIndex(
                (e) => `${e.vendor}::${e.cls ?? e.tool}` === key
              );
              const next: PullEntry = {
                vendor: ev.vendor,
                tool: ev.tool,
                cls: ev.class,
                query: ev.query,
                status: ev.status,
                results: ev.results,
                durationMs: ev.duration_ms,
                path: ev.path,
                error: ev.error,
              };
              if (idx >= 0) {
                const out = prev.slice();
                out[idx] = next;
                return out;
              }
              return [...prev, next];
            });
          }
          break;
        }
        case "clean": {
          if ("phase" in ev) {
            if (ev.phase === "start") setCleanPhase("running");
            else if (ev.phase === "done") {
              setCleanPhase("done");
              setPromotePhase("running");
              setCleanSummary({
                kept: ev.kept,
                rejected: ev.rejected,
                candidates: ev.candidates,
              });
            } else if (ev.phase === "noop") {
              setCleanPhase("done");
              setPromotePhase("running");
              setCleanSummary({ kept: 0, rejected: 0, candidates: 0 });
            }
          } else if ("verdict" in ev) {
            setCleanEntries((prev) => [
              ...prev,
              {
                vendor: ev.vendor,
                metric: ev.metric,
                verdict: ev.verdict,
                reason: ev.reason,
                title: ev.title,
              },
            ]);
          }
          break;
        }
        case "promote": {
          if ("phase" in ev) {
            if (ev.phase === "start") setPromotePhase("running");
            else if (ev.phase === "done") {
              setPromotePhase("done");
              setPromoteSummary({
                rowsWritten: ev.rows_written,
                failures: ev.failures,
              });
            }
          } else if ("status" in ev) {
            setPromoteEntries((prev) => [
              ...prev,
              {
                vendor: ev.vendor,
                status: ev.status,
                rowsWritten: ev.rows_written,
                rowsAttempted: ev.rows_attempted,
                error: ev.error,
              },
            ]);
          }
          break;
        }
        case "complete":
          setSummary(ev.summary);
          completedRef.current = true;
          break;
        case "error":
          setStreamError(ev.message);
          break;
      }
    }

    return () => {
      es.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return (
    <div
      className="fixed inset-0 z-40 bg-overlay-strong flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-base border border-rule rounded-lg w-full max-w-4xl max-h-[88vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-5 py-4 border-b border-rule flex items-baseline justify-between gap-4">
          <div>
            <h2 className="text-ink-primary text-sm font-semibold uppercase tracking-wider">
              Daily agent run
            </h2>
            <p className="text-ink-dim text-[10px] mt-0.5">
              Pull → Clean → Promote · job{" "}
              <span className="text-ink-muted">{jobId}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink-primary text-xs"
          >
            close ✕
          </button>
        </header>

        <div className="px-5 py-4 space-y-5">
          <Stage
            label="Pull"
            ordinal={1}
            phase={pullPhase}
            runningLine="MCP calls firing…"
            summary={
              pullSummary
                ? `${pullSummary.rowsPulled} rows pulled · ` +
                  `${pullSummary.failures} failures · ` +
                  `${pullSummary.fallbackCalls} fallback call${
                    pullSummary.fallbackCalls === 1 ? "" : "s"
                  }`
                : null
            }
          >
            {pullEntries.map((e, i) => (
              <PullRow key={`${e.vendor}-${e.cls ?? e.tool}-${i}`} entry={e} />
            ))}
          </Stage>

          <Stage
            label="Clean"
            ordinal={2}
            phase={cleanPhase}
            runningLine="AI validator evaluating event candidates…"
            summary={
              cleanSummary
                ? cleanSummary.candidates === 0
                  ? "no event candidates to validate"
                  : `${cleanSummary.kept} kept · ${cleanSummary.rejected} rejected ` +
                    `(${cleanSummary.candidates} candidate${
                      cleanSummary.candidates === 1 ? "" : "s"
                    })`
                : null
            }
          >
            {cleanEntries.map((e, i) => (
              <CleanRow key={i} entry={e} />
            ))}
          </Stage>

          <Stage
            label="Promote"
            ordinal={3}
            phase={promotePhase}
            runningLine="Writing rows to Airtable…"
            summary={
              promoteSummary
                ? `${promoteSummary.rowsWritten} rows written · ` +
                  `${promoteSummary.failures} failure${
                    promoteSummary.failures === 1 ? "" : "s"
                  }`
                : null
            }
          >
            {promoteEntries.map((e, i) => (
              <PromoteRow key={i} entry={e} />
            ))}
          </Stage>

          {summary && <SummaryCard summary={summary} />}

          {streamError && !summary && (
            <div className="bg-surface border border-signal-red/40 rounded-lg px-4 py-3 text-sm">
              <p className="text-signal-red font-medium">stream error</p>
              <p className="text-ink-muted text-xs mt-1">{streamError}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage container
// ---------------------------------------------------------------------------

function Stage({
  label,
  ordinal,
  phase,
  runningLine,
  summary,
  children,
}: {
  label: string;
  ordinal: number;
  phase: Phase;
  runningLine: string;
  summary: string | null;
  children: React.ReactNode;
}) {
  const dotClass =
    phase === "done"
      ? "bg-signal-teal"
      : phase === "running"
      ? "bg-signal-amber"
      : "bg-ink-dim";

  return (
    <section className="bg-surface border border-rule rounded-lg">
      <header className="px-4 py-2.5 border-b border-rule flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${dotClass}`}
          />
          <span className="text-ink-muted text-[10px] uppercase tracking-wider">
            Step {ordinal} · {label}
          </span>
        </div>
        <span className="text-[10px] text-ink-muted">
          {phase === "done"
            ? summary ?? "complete"
            : phase === "running"
            ? runningLine
            : "pending"}
        </span>
      </header>
      <div className="px-4 py-2.5 font-mono text-[11px] leading-relaxed space-y-1">
        {React.Children.count(children) === 0 && phase !== "idle" ? (
          <div className="text-ink-dim italic">awaiting first event…</div>
        ) : React.Children.count(children) === 0 ? (
          <div className="text-ink-dim italic">queued</div>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Per-stage row renderers
// ---------------------------------------------------------------------------

function PullRow({ entry }: { entry: PullEntry }) {
  const tone =
    entry.status === "done"
      ? "text-signal-teal"
      : entry.status === "failed"
      ? "text-signal-red"
      : "text-signal-amber";
  const marker =
    entry.status === "done" ? "✓" : entry.status === "failed" ? "✗" : "▸";
  return (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span className={`${tone} w-3 inline-block`}>{marker}</span>
      <span className="text-ink-muted">[{entry.tool}]</span>
      <span className="text-ink-primary">{entry.vendor}</span>
      {entry.cls && <span className="text-ink-dim">·</span>}
      {entry.cls && <span className="text-ink-muted">{entry.cls}</span>}
      {entry.status !== "firing" && entry.results !== undefined && (
        <>
          <span className="text-ink-dim">·</span>
          <span className="text-ink-muted">
            {entry.results} result{entry.results === 1 ? "" : "s"}
          </span>
        </>
      )}
      {entry.durationMs !== undefined && entry.durationMs > 0 && (
        <>
          <span className="text-ink-dim">·</span>
          <span className="text-ink-dim tabular-nums">
            {entry.durationMs}ms
          </span>
        </>
      )}
      {entry.path && entry.path !== "search_engine" && (
        <>
          <span className="text-ink-dim">·</span>
          <span className="text-signal-amber">{entry.path}</span>
        </>
      )}
      {entry.status === "failed" && entry.error && (
        <span className="text-signal-red ml-2 truncate">{entry.error}</span>
      )}
    </div>
  );
}

function CleanRow({ entry }: { entry: CleanEntry }) {
  const kept = entry.verdict === "kept";
  const tone = kept ? "text-signal-teal" : "text-ink-dim";
  const marker = kept ? "✓" : "✗";
  return (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span className={`${tone} w-3 inline-block`}>{marker}</span>
      <span className="text-ink-primary">{entry.vendor}</span>
      <span className="text-ink-dim">·</span>
      <span className="text-ink-muted">{entry.metric}</span>
      <span className="text-ink-dim">·</span>
      <span className={kept ? "text-signal-teal" : "text-ink-muted"}>
        {entry.verdict.toUpperCase()}
      </span>
      <span className="text-ink-dim flex-1 truncate">{entry.reason}</span>
    </div>
  );
}

function PromoteRow({ entry }: { entry: PromoteEntry }) {
  const ok = entry.status === "done";
  const tone = ok ? "text-signal-teal" : "text-signal-red";
  const marker = ok ? "✓" : "✗";
  return (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span className={`${tone} w-3 inline-block`}>{marker}</span>
      <span className="text-ink-primary">{entry.vendor}</span>
      <span className="text-ink-dim">·</span>
      {ok ? (
        <span className="text-ink-muted tabular-nums">
          {entry.rowsWritten} row{entry.rowsWritten === 1 ? "" : "s"} written
        </span>
      ) : (
        <>
          <span className="text-signal-red">failed</span>
          {entry.rowsAttempted !== undefined && (
            <>
              <span className="text-ink-dim">·</span>
              <span className="text-ink-muted">
                {entry.rowsAttempted} row{entry.rowsAttempted === 1 ? "" : "s"}{" "}
                attempted
              </span>
            </>
          )}
          {entry.error && (
            <span className="text-signal-red ml-2 truncate">
              {entry.error}
            </span>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Final summary card
// ---------------------------------------------------------------------------

function SummaryCard({ summary }: { summary: AgentSummary }) {
  const anyFailures = summary.failures.length > 0;
  return (
    <section
      className={`bg-surface border rounded-lg px-4 py-3 ${
        anyFailures ? "border-signal-amber/40" : "border-signal-teal/40"
      }`}
    >
      <header className="flex items-baseline justify-between mb-2">
        <span
          className={`text-[10px] uppercase tracking-wider font-medium ${
            anyFailures ? "text-signal-amber" : "text-signal-teal"
          }`}
        >
          Run complete
        </span>
        <span className="text-[10px] text-ink-dim tabular-nums">
          {summary.capture_date} · {summary.elapsed_seconds}s
        </span>
      </header>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <Stat label="rows written" value={summary.rows_written} />
        <Stat label="events kept" value={summary.events_kept} />
        <Stat label="events rejected" value={summary.events_rejected} />
        <Stat label="fallback calls" value={summary.fallback_calls} />
      </dl>
      {anyFailures && (
        <div className="mt-3 pt-3 border-t border-rule">
          <p className="text-[10px] uppercase tracking-wider text-signal-amber mb-1">
            failures ({summary.failures.length})
          </p>
          <ul className="font-mono text-[11px] space-y-1">
            {summary.failures.map((f, i) => (
              <li key={i} className="flex items-baseline gap-2">
                <span className="text-signal-red">✗</span>
                <span className="text-ink-primary">{f.vendor}</span>
                <span className="text-ink-dim flex-1 truncate">{f.error}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-ink-primary text-lg font-bold tabular-nums leading-none">
        {value}
      </div>
      <div className="text-ink-dim text-[10px] uppercase tracking-wider mt-1">
        {label}
      </div>
    </div>
  );
}

