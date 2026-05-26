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
  score: number;
  state: RiskState;
  convergence_count: number;
  signal_count: number;
  latest_capture: string | null;
  trajectory: TrajectoryPoint[];
  components: ComponentScore[];
}

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
