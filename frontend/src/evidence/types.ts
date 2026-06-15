// Types mirror the ESG Evidence Engine JSON (backend/out/*.json). Every surfaced
// number carries a trace; missing data is null (never a fabricated 0).

export type QuadrantKey =
  | "HIDDEN_WINNERS"
  | "FUTURE_LEADERS"
  | "VALUE_TRAPS"
  | "OVERRATED";

export type VerifyState = "VERIFIED" | "ASSERTED" | "ABSENT";
export type RegQuality = "MET" | "PARTIAL" | "MISSING" | "NA";

export type TraceNode = {
  label: string;
  value: number | null;
  contribution: number | null;
  source_sentence: string | null;
  source_doc: string | null;
  source_page: number | null;
  children: TraceNode[];
};

// kept for the legacy CandlestickChart primitive
export type Candle = {
  label?: string;
  week_date?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
};

export type RegCell = {
  reg_id: string;
  name: string;
  status: RegQuality;
};

export type CompanyRow = {
  id: string;
  name: string;
  ticker: string;
  sector: string;
  country: string;
  evidence_total: number | null;
  confidence: number;
  consensus: number | null;
  divergence: number | null;
  evidence_gap: number | null;
  momentum: number | null;
  quadrant: QuadrantKey | null;
  is_underpriced_improver: boolean;
  compliance_score: number | null;
  forecast: number | null;
  regulations?: RegCell[] | null;
};

export type RegulationInfo = {
  reg_id: string;
  name: string;
  jurisdiction: string;
  scope: string;
  requirement: string;
  effective_year: number;
  applies_to: string;
  n_applicable: number;
  n_met: number;
  n_partial: number;
  n_missing: number;
  n_na: number;
};

export type MatrixPoint = {
  id: string;
  name: string;
  x: number | null;
  y: number | null;
  quadrant: QuadrantKey | null;
  size: number | null;
  is_underpriced_improver: boolean;
};

export type EvidenceScore = {
  company_id: string;
  year: number;
  total: number | null;
  pillars: { E: number | null; S: number | null; G: number | null };
  confidence: number;
  absent_topics: string[];
  trace: TraceNode;
};

export type SeriesPoint = {
  year: number;
  total: number | null;
  pillars: Record<string, number | null>;
  confidence: number;
};

export type Raters = {
  company_id: string;
  msci_pct: number | null;
  sp_pct: number | null;
  sustainalytics_pct: number | null;
  consensus: number | null;
  divergence: number | null;
};

export type Signal = {
  company_id: string;
  proof_up: boolean | null;
  opinion_flat: boolean | null;
  price_flat: boolean | null;
  is_underpriced_improver: boolean;
  evidence_gap: number | null;
  momentum: number | null;
  esg_today: number | null;
  quadrant: QuadrantKey | null;
  trace: TraceNode;
};

export type Candle2 = {
  week_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

export type BandSpan = {
  start_date: string;
  end_date: string;
  slope: number;
  start_score: number;
  end_score: number;
};

export type WitnessPin = {
  date: string;
  type: "emissions_verified" | "hiring_surge" | "rater_unchanged" | "controversy";
  label: string;
  trace_ref: TraceNode;
};

export type Witness = {
  company_id: string;
  candles: Candle2[];
  band: BandSpan[];
  pins: WitnessPin[];
  benchmark: Candle2[];
  flat: {
    stock_return: number | null;
    sti_return: number | null;
    rel_return: number | null;
    is_flat: boolean | null;
  };
};

export type RegStatus = {
  reg_id: string;
  name: string;
  status: RegQuality;
  evidence_ref: string | null;
};

export type Compliance = {
  company_id: string;
  score: number | null;
  met: RegStatus[];
  partial: RegStatus[];
  missing: RegStatus[];
  not_in_force: RegStatus[];
  trace: TraceNode;
};

export type FeatureContribution = {
  feature: string;
  value: number | null;
  contribution: number;
};

export type Forecast = {
  company_id: string;
  predicted_score: number | null;
  horizon_years: number;
  ci_low: number | null;
  ci_high: number | null;
  feature_contributions: FeatureContribution[];
  val_error: number | null;
  hypothesis: boolean;
  trace: TraceNode;
};

export type ClaimRow = {
  topic_id: string;
  pillar: string;
  state: VerifyState;
  text: string;
  source_sentence: string | null;
  source_doc: string | null;
  source_url?: string | null;
  source_page: number | null;
  weight: number;
};

export type NewsItem = {
  title: string;
  url: string | null;
  label: "controversy" | "positive" | "stock" | "neutral";
};
export type NewsCompany = {
  company_id: string;
  name: string;
  sector?: string | null;
  ticker?: string | null;
  n_items: number;
  controversy: number;
  positive: number;
  sentiment: number;
  fetched_at?: string | null;
  headlines: NewsItem[];
};
export type NewsData = { source?: string; last_run?: string | null; companies: NewsCompany[] };

export type CompanyDetail = {
  company: {
    company_id: string;
    ticker: string;
    name: string;
    country: string;
    exchange: string;
    sector: string;
    sasb_industry: string;
    scope: string;
  };
  evidence: EvidenceScore;
  series: SeriesPoint[];
  raters: Raters;
  signal: Signal;
  witness: Witness;
  compliance: Compliance;
  forecast: Forecast;
  claims: {
    claims: ClaimRow[];
    absent: { topic_id: string; state: string }[];
    live?: boolean;
    source_url?: string;
    source_title?: string;
  };
  peers: { id: string; name: string; evidence_total: number | null }[];
};
