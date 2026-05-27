import { useEffect } from "react";
import type { TrustAudit } from "../types";

interface Props {
  audit: TrustAudit;
  onClose: () => void;
}

/**
 * Per-vendor citation audit breakdown. Opened from the trust badge in
 * FleetOverview. Reuses the audit data already fetched there — no new
 * network calls.
 */
export function TrustAuditModal({ audit, onClose }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const allPass = audit.unresolved === 0 && audit.all_pass;

  return (
    <div
      className="fixed inset-0 bg-overlay-strong z-40 flex items-start justify-center pt-24 px-4"
      onClick={onClose}
    >
      <div
        className="bg-base border border-rule rounded-lg w-full max-w-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-rule px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`text-lg leading-none ${
                allPass ? "text-signal-blue" : "text-signal-amber"
              }`}
              aria-hidden="true"
            >
              {allPass ? "✓" : "⚠"}
            </span>
            <h2 className="text-base font-semibold text-ink-primary">
              Citation Audit Report
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink-primary text-sm"
            aria-label="Close"
          >
            close ✕
          </button>
        </div>

        {/* Aggregate stats */}
        <div className="px-5 py-4 border-b border-rule grid grid-cols-4 gap-4">
          <Stat
            label="AI claims"
            value={audit.total_claims}
            tone="primary"
          />
          <Stat
            label="Sources available"
            value={audit.total_citations}
            tone="primary"
          />
          <Stat
            label="Unresolved"
            value={audit.unresolved}
            tone={audit.unresolved === 0 ? "good" : "bad"}
          />
          <Stat
            label="Vendors audited"
            value={audit.vendor_audits.length}
            tone="primary"
          />
        </div>

        {/* Per-vendor table */}
        <div className="px-5 py-4">
          <p className="text-[10px] uppercase tracking-wider text-ink-muted mb-2">
            Per-vendor breakdown
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-ink-dim text-[10px] uppercase tracking-wider border-b border-rule">
                <th className="text-left font-normal pb-2">Vendor</th>
                <th className="text-right font-normal pb-2">Claims</th>
                <th className="text-right font-normal pb-2">Sources</th>
                <th className="text-right font-normal pb-2">Unresolved</th>
                <th className="text-right font-normal pb-2">Audit</th>
              </tr>
            </thead>
            <tbody>
              {audit.vendor_audits.map((v) => (
                <tr
                  key={v.vendor}
                  className="border-b border-rule/50 last:border-b-0"
                >
                  <td className="py-2 text-ink-primary">{v.vendor}</td>
                  <td className="text-right font-mono text-ink-primary tabular-nums">
                    {v.claims_cited}
                  </td>
                  <td className="text-right font-mono text-ink-muted tabular-nums">
                    {v.sources_available}
                  </td>
                  <td
                    className={`text-right font-mono tabular-nums ${
                      v.unresolved === 0
                        ? "text-ink-muted"
                        : "text-signal-amber font-medium"
                    }`}
                  >
                    {v.unresolved}
                  </td>
                  <td className="text-right">
                    <AuditPill pass={v.audit_pass} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer note */}
        <div className="border-t border-rule px-5 py-3 text-[11px] text-ink-dim leading-relaxed">
          Stable vendors generate no AI summary and are excluded. The
          audit verifies every <code className="text-ink-muted">[N]</code>{" "}
          citation marker in the narrative resolves to a numbered source
          in the evidence list.
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "primary" | "good" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-signal-blue"
      : tone === "bad"
        ? "text-signal-amber"
        : "text-ink-primary";
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-ink-muted mb-1">
        {label}
      </p>
      <p className={`text-2xl font-mono tabular-nums ${toneClass}`}>
        {value}
      </p>
    </div>
  );
}

function AuditPill({ pass }: { pass: boolean }) {
  return pass ? (
    <span className="inline-block text-[10px] uppercase tracking-wider font-semibold bg-signal-teal/15 border border-signal-teal/40 text-signal-teal px-2 py-0.5 rounded">
      pass
    </span>
  ) : (
    <span className="inline-block text-[10px] uppercase tracking-wider font-semibold bg-signal-amber/15 border border-signal-amber/40 text-signal-amber px-2 py-0.5 rounded">
      fail
    </span>
  );
}
