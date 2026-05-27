export type RiskState = "stable" | "warning" | "critical";

export interface TrajectoryPoint {
  date: string;
  score: number;
  state: RiskState;
}

export interface ComponentScore {
  name: string;
  score: number;
  weight: number;
  contribution: number;
  drivers: string[];
}

export interface VendorOverview {
  name: string;
  type: string;
  is_demo: boolean;
  is_removable: boolean;
  cik: string | null;
  ticker: string | null;
  score: number;
  state: RiskState;
  convergence_count: number;
  signal_count: number;
  latest_capture: string | null;
  trajectory: TrajectoryPoint[];
  components: ComponentScore[];
}

export interface LookupMatch {
  name: string;
  cik: string;
  ticker: string;
  match_confidence: number;
}

export interface VendorLookupResponse {
  query: string;
  matches: LookupMatch[];
}

export const VENDOR_TYPES = [
  "Payments",
  "Bank Data",
  "Cloud Infra",
  "Comms/2FA",
  "Data Infra",
  "Payments/BaaS",
  "Other",
] as const;
export type VendorType = (typeof VENDOR_TYPES)[number];

export interface Citation {
  n: number;
  metric: string;
  capture_date: string | null;
  source_url: string;
  snippet: string;
}

export interface RiskSummary {
  headline: string;
  sentiment_read: string;
  narrative: string;
  recommended_action: string;
  alert_type: string;
  generated_by: string;
  parse_error: string;
  citations: Citation[];
  audit: {
    cited: number[];
    available: number[];
    invalid: number[];
    uncited: number[];
    all_claims_sourced: boolean;
  };
}

export interface RecentSignal {
  capture_date: string | null;
  metric: string | null;
  value: string | null;
  unit: string | null;
  sentiment: string | null;
  source_url: string | null;
  notes: string | null;
}

export interface VendorDetail {
  overview: VendorOverview;
  alert: {
    fired: boolean;
    alert_type: string | null;
    headline: string | null;
    fired_at: string | null;
  };
  summary: RiskSummary | null;
  recent_signals: RecentSignal[];
}

// -------- Agent pipeline ----------------------------------------------------
// Per-step events streamed from the backend during a Pull → Clean → Promote
// run. The shape mirrors what `foreshock/agent.py` emits.

export type AgentEvent =
  | { step: "pull"; phase: "start"; vendors: string[] }
  | { step: "pull"; phase: "done"; rows_pulled: number; failures: number; fallback_calls: number }
  | { step: "pull"; phase?: "session_failed"; error?: string }
  | {
      step: "pull";
      vendor: string;
      tool: string;
      class?: string;
      query?: string;
      status: "firing" | "done" | "failed";
      results?: number;
      duration_ms?: number;
      path?: string;
      error?: string;
      note?: string;
    }
  | { step: "clean"; phase: "start" | "noop"; reason?: string }
  | { step: "clean"; phase: "done"; kept: number; rejected: number; candidates: number }
  | {
      step: "clean";
      vendor: string;
      metric: string;
      verdict: "kept" | "rejected";
      reason: string;
      title?: string;
    }
  | { step: "promote"; phase: "start"; rows_to_write: number }
  | { step: "promote"; phase: "done"; rows_written: number; failures: number }
  | {
      step: "promote";
      vendor: string;
      status: "done" | "failed";
      rows_written?: number;
      rows_attempted?: number;
      error?: string;
    }
  | { step: "complete"; summary: AgentSummary }
  | { step: "error"; message: string }
  | { type: "stream_end" }
  | { type: "timeout" };

export interface AgentSummary {
  rows_written: number;
  events_kept: number;
  events_rejected: number;
  fallback_calls: number;
  elapsed_seconds: number;
  capture_date: string;
  failures: { vendor: string; error: string }[];
}

export interface TrustAuditVendor {
  vendor: string;
  claims_cited: number;
  sources_available: number;
  unresolved: number;
  audit_pass: boolean;
}

export interface TrustAudit {
  total_claims: number;
  total_citations: number;
  unresolved: number;
  all_pass: boolean;
  vendor_audits: TrustAuditVendor[];
}

export interface FleetSummary {
  headline: string;
  narrative: string;
  generated_by: string;
  parse_error: string;
  fleet_counts: {
    critical: number;
    warning: number;
    stable: number;
    total: number;
  };
}

export interface SystemStatus {
  monitoring_active: boolean;
  vendor_count: number;
  signal_count_total: number;
  last_capture: string | null;
  live_pull_query: string;
  live_pull_vendor: string;
}

// SSE event payloads emitted by /live-pull/stream. The honesty boundary
// lives here: `mcp_call` / `mcp_result` only appear in live mode;
// `fixture_read` / `fixture_loaded` only in seeded mode.
export type FlowEvent =
  | { type: "start"; mode: "live" | "seeded"; capture_date: string; label: string }
  | { type: "mcp_call"; tool: string; vendor: string; query: string; status: string; data_path: "bright-data-mcp" }
  | { type: "mcp_result"; tool: string; vendor: string; results_count: number; duration_ms: number; status: string; data_path: "bright-data-mcp" }
  | { type: "fixture_read"; fixture: string; label: "cached_replay"; status: string; data_path: "local-disk" }
  | { type: "fixture_loaded"; fixture: string; label: "cached_replay"; results_count: number; data_path: "local-disk" }
  | { type: "save_seed"; fixture: string; results_count: number }
  | { type: "rows_built"; category: "real_vendor" | "veridian_finale"; vendor: string; count: number; metrics: string[]; note?: string }
  | { type: "airtable_write"; status: "started" | "ok"; row_count?: number; rows_written?: number }
  | { type: "complete"; mode: "live" | "seeded"; capture_date: string; real_vendor_rows: number; veridian_rows: number; rows_written: number; saved_seed: boolean }
  | { type: "error"; stage?: string; tool?: string; message: string }
  | { type: "stream_end" };
