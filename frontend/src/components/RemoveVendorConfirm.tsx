import { useEffect, useState } from "react";
import { removeVendor } from "../lib/api";

interface Props {
  vendorName: string;
  onCancel: () => void;
  onRemoved: () => void;
}

export function RemoveVendorConfirm({ vendorName, onCancel, onRemoved }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, submitting]);

  async function handleConfirm() {
    setError(null);
    setSubmitting(true);
    try {
      await removeVendor(vendorName);
      onRemoved();
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-overlay-strong z-50 flex items-center justify-center px-4"
      onClick={() => !submitting && onCancel()}
    >
      <div
        className="bg-base border border-rule rounded-lg w-full max-w-sm shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 space-y-3">
          <h2 className="text-sm font-semibold text-ink-primary">
            Remove {vendorName} from monitoring?
          </h2>
          <p className="text-xs text-ink-muted leading-relaxed">
            Signal history is preserved in the audit record. The vendor is
            deactivated, not deleted — re-adding by the same name brings it
            back with its history intact.
          </p>
          {error && (
            <p className="text-xs text-signal-red bg-signal-red/10 border border-signal-red/30 rounded p-2">
              {error}
            </p>
          )}
        </div>
        <div className="border-t border-rule px-5 py-3 flex items-center justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="text-xs px-3 py-1.5 rounded text-ink-muted hover:text-ink-primary disabled:opacity-40"
          >
            cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="text-xs px-3 py-1.5 rounded bg-signal-red text-white font-medium hover:bg-signal-red/90 disabled:opacity-40"
          >
            {submitting ? "removing…" : "remove vendor"}
          </button>
        </div>
      </div>
    </div>
  );
}
