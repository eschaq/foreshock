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
