import { useEffect, useState } from "react";
import { fetchVendorDetail } from "../lib/api";
import type { VendorDetail } from "../types";
import { CitedText } from "./CitedText";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

interface Props {
  vendorName: string;
  onClose: () => void;
}

export function DetailPanel({ vendorName, onClose }: Props) {
  const [detail, setDetail] = useState<VendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    fetchVendorDetail(vendorName)
      .then((d) => {
        if (active) setDetail(d);
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [vendorName]);

  return (
    <div
      className="fixed inset-0 bg-overlay-strong z-30 flex justify-end"
      onClick={onClose}
    >
      <div
        className="bg-base border-l border-rule w-full max-w-3xl h-full overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-base border-b border-rule px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-ink-primary">
            {vendorName}
          </h2>
          <div className="flex items-center gap-4">
            <a
              href={`/api/vendors/${encodeURIComponent(vendorName)}/report.pdf`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-signal-blue/40 text-signal-blue hover:bg-signal-blue/10 transition-colors"
              title="Generate a DORA-Article-28-style evidence-artifact PDF (example output — not validated regulatory compliance)"
            >
              <PdfIcon />
              Export DORA evidence (PDF)
            </a>
            <button
              onClick={onClose}
              className="text-ink-muted hover:text-ink-primary text-sm"
            >
              close ✕
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {loading && (
            <div className="text-ink-muted text-sm">
              loading vendor detail and (if needed) generating live AI
              summary…
            </div>
          )}
          {error && (
            <div className="text-signal-red text-sm">error: {error}</div>
          )}
          {detail && <DetailBody detail={detail} />}
        </div>
      </div>
    </div>
  );
}

function DetailBody({ detail }: { detail: VendorDetail }) {
  const { overview, alert, summary, recent_signals } = detail;

  return (
    <>
      <section className="flex items-end justify-between gap-6">
        <div>
          <p className="text-ink-muted text-xs">{overview.type}</p>
          <div className="flex items-baseline gap-3 mt-1">
            <span className="text-ink-primary text-4xl font-bold tabular-nums">
              {overview.score.toFixed(1)}
            </span>
            <StateBadge state={overview.state} />
          </div>
          <p className="text-ink-dim text-xs mt-1">
            convergence: {overview.convergence_count} · {overview.signal_count}{" "}
            signals · latest {overview.latest_capture ?? "—"}
          </p>
        </div>
        <Sparkline points={overview.trajectory} width={220} height={56} />
      </section>

      {/* Score component breakdown */}
      <section>
        <h3 className="text-ink-muted text-xs uppercase tracking-wider mb-2">
          Score components
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-dim">
              <th className="text-left font-normal">component</th>
              <th className="text-right font-normal">score</th>
              <th className="text-right font-normal">weight</th>
              <th className="text-right font-normal">contrib</th>
              <th className="text-left font-normal pl-4">drivers</th>
            </tr>
          </thead>
          <tbody>
            {overview.components.map((c) => (
              <tr key={c.name} className="border-t border-rule">
                <td className="py-1 text-ink-primary">{c.name}</td>
                <td className="text-right tabular-nums text-ink-muted">
                  {c.score.toFixed(1)}
                </td>
                <td className="text-right tabular-nums text-ink-muted">
                  {c.weight.toFixed(2)}
                </td>
                <td className="text-right tabular-nums text-ink-primary">
                  {c.contribution.toFixed(1)}
                </td>
                <td className="text-ink-muted pl-4 text-xs">
                  {c.drivers.length === 0 ? "—" : c.drivers.join("; ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* AI risk summary (only when alert fired) */}
      {alert.fired && summary && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-ink-muted text-xs uppercase tracking-wider">
              AI risk summary
            </h3>
            <span
              className={`text-[10px] ${
                summary.audit.all_claims_sourced
                  ? "text-signal-teal"
                  : "text-signal-red"
              }`}
            >
              {summary.audit.all_claims_sourced
                ? "✓ all claims sourced"
                : `✗ ${summary.audit.invalid.length} unsourced`}
            </span>
          </div>

          <div className="bg-surface border border-rule rounded-lg p-4 space-y-4 text-sm leading-relaxed">
            <p className="text-ink-primary font-medium">
              <CitedText
                text={summary.headline}
                citations={summary.citations}
              />
            </p>

            <Block label="Sentiment read">
              <CitedText
                text={summary.sentiment_read}
                citations={summary.citations}
              />
            </Block>

            <Block label="Narrative">
              {summary.narrative.split("\n\n").map((p, i) => (
                <p key={i} className="mb-2 last:mb-0">
                  <CitedText text={p} citations={summary.citations} />
                </p>
              ))}
            </Block>

            <Block label="Recommended action">
              <CitedText
                text={summary.recommended_action}
                citations={summary.citations}
              />
            </Block>
          </div>

          {/* Sources — the trust contract, visible */}
          <h3 className="text-ink-muted text-xs uppercase tracking-wider mt-6 mb-2">
            Sources ({summary.citations.length})
          </h3>
          <ol className="space-y-2">
            {summary.citations.map((c) => (
              <li
                key={c.n}
                id={`source-${c.n}`}
                className="bg-surface border border-rule rounded p-3 text-xs"
              >
                <div className="flex items-start gap-2">
                  <span className="text-signal-blue font-medium tabular-nums">[{c.n}]</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-ink-muted">
                      <span className="text-ink-primary">{c.metric}</span> ·{" "}
                      {c.capture_date}
                    </div>
                    {c.snippet && (
                      <div className="text-ink-muted mt-0.5">{c.snippet}</div>
                    )}
                    <a
                      href={
                        c.source_url.startsWith("http") ? c.source_url : "#"
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className={
                        c.source_url.startsWith("http")
                          ? "text-signal-blue hover:underline break-all mt-0.5 inline-block"
                          : "text-ink-dim break-all italic mt-0.5 inline-block"
                      }
                    >
                      {c.source_url}
                    </a>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {!alert.fired && (
        <section className="bg-surface border border-rule rounded p-4 text-sm text-ink-muted">
          No active alert — this vendor is stable. AI summary not generated.
        </section>
      )}

      {/* Recent signals (raw evidence) */}
      <section>
        <h3 className="text-ink-muted text-xs uppercase tracking-wider mb-2">
          Recent signals ({recent_signals.length})
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-ink-dim">
                <th className="text-left font-normal py-1">date</th>
                <th className="text-left font-normal py-1">metric</th>
                <th className="text-left font-normal py-1">value</th>
                <th className="text-left font-normal py-1">notes</th>
              </tr>
            </thead>
            <tbody>
              {recent_signals.map((s, i) => (
                <tr
                  key={i}
                  className="border-t border-rule align-top"
                >
                  <td className="py-1 text-ink-muted whitespace-nowrap pr-2 tabular-nums">
                    {s.capture_date}
                  </td>
                  <td className="text-ink-primary pr-2 whitespace-nowrap">
                    {s.metric}
                  </td>
                  <td className="text-ink-muted pr-2 max-w-[200px] truncate">
                    {s.value}
                  </td>
                  <td className="text-ink-muted">
                    <span className="block max-w-md truncate">
                      {s.notes}
                    </span>
                    {s.source_url && s.source_url.startsWith("http") && (
                      <a
                        href={s.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-signal-blue hover:underline text-[10px] break-all"
                      >
                        {s.source_url}
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function PdfIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="12" y1="18" x2="12" y2="12" />
      <polyline points="9 15 12 12 15 15" />
    </svg>
  );
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-ink-dim text-[10px] uppercase tracking-wider mb-1">
        {label}
      </p>
      <div className="text-ink-primary">{children}</div>
    </div>
  );
}
