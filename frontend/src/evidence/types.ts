// Types mirror the ESG Evidence Engine JSON (backend/out/*.json). Every surfaced
// number carries a trace; missing data is null (never a fabricated 0).

export type QuadrantKey =
  | "HIDDEN_WINNERS"
  | "FUTURE_LEADERS"
  | "VALUE_TRAPS"
  | "OVERRATED";

export type VerifyState = "VERIFIED" | "ASSERTED" | "INFERRED" | "ABSENT";
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
  rating_total: number | null;           // headline ESG rating (agency consensus, SASB-weighted)
  rating_provenance?: Provenance | null;
  rating_coverage?: number | null;
  price?: number | null;                 // last close (local currency)
  price_chg?: number | null;             // weekly % change
  spark?: number[] | null;               // recent closes for the trend sparkline
  evidence_total: number | null;
  confidence: number;
  consensus: number | null;
  divergence: number | null;
  evidence_gap: number | null;
  momentum: number | null;               // redefined: emission momentum (decarbonising = +)
  emission_momentum?: number | null;
  quadrant: QuadrantKey | null;
  is_underpriced_improver: boolean;
  compliance_score: number | null;
  compliance_provenance?: Provenance | null;
  forecast: number | null;                 // predicted MSCI level, CCC=1 .. AAA=7
  forecast_label?: string | null;          // that level as a letter
  forecast_direction?: string | null;      // "likely upgrade" | "likely hold" | ...
  forecast_baseline_only?: boolean;
  forecast_provenance?: Provenance | null;
  forecast_accuracy_note?: string | null;
  rater_provenance?: Provenance | null;
  benchmark_total?: number | null;
  benchmark_source?: string | null;
  benchmark_peers?: number | null;
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
  n_scraped: number;
  source_url: string | null;
  source_excerpt: string | null;
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

// The ESG RATING: agency consensus (MSCI / Sustainalytics / CDP), SASB-material-weighted,
// on one 0..100 quality scale. This is the headline ESG score (replaces evidence.total).
export type RatingScore = {
  company_id: string;
  year: number;
  total: number | null;
  pillars: { E: number | null; S: number | null; G: number | null };
  coverage: number;
  contributions: Record<string, number>;
  topic_breakdown: {
    topic_id: string; name: string; pillar: "E" | "S" | "G";
    weight: number; score: number | null; contribution: number | null;
  }[];
  agencies: string[];
  provenance: Provenance | null;
  trace: TraceNode;
};

export type RatingSeriesPoint = {
  year: number;
  total: number | null;
  pillars: Record<string, number | null>;
  provenance: Provenance | null;
};

// ESRS double-materiality composite: financial (ESG rating) × impact (carbon intensity) − greenwashing.
export type DoubleMateriality = {
  company_id: string;
  financial: number | null;
  impact: number | null;
  composite: number | null;
  weight_financial: number;
  weight_impact: number;
  carbon_intensity: number | null;
  intensity_rank: number | null;
  intensity_peers: number | null;
  greenwashing_penalty: number;
  greenwashing_drivers: { label: string; points: number; detail: string }[];
  greenwashing_headlines?: { title: string; source: string; url: string }[];
  under_attributed: boolean;
  provenance: Provenance | null;
  note: string | null;
};

// Real Yahoo fundamentals — the CGS-investor finance panel (ported from smartass).
export type CompanyFundamentals = {
  profile: {
    name: string | null; sector: string | null; industry: string | null;
    employees: number | null; summary: string | null; website: string | null;
    city: string | null; country: string | null; ceo: string | null; exchange: string | null;
  };
  financials: {
    currency: string | null; market_cap: number | null; market_cap_fmt: string | null;
    enterprise_value: number | null; revenue: number | null; revenue_fmt: string | null;
    ebitda: number | null; gross_margin: number | null; operating_margin: number | null;
    profit_margin: number | null; roe: number | null; roa: number | null;
    revenue_growth: number | null; debt_to_equity: number | null;
    free_cashflow: number | null; current_ratio: number | null;
  };
  valuation: {
    trailing_pe: number | null; forward_pe: number | null; price_to_book: number | null;
    peg: number | null; ev_to_ebitda: number | null; eps_trailing: number | null;
    book_value: number | null; beta: number | null; dividend_yield: number | null;
    dividend_rate: number | null; payout_ratio: number | null;
    fifty_two_high: number | null; fifty_two_low: number | null;
  };
  ratings: {
    recommendation: string | null; recommendation_mean: number | null; n_analysts: number | null;
    target_mean: number | null; target_high: number | null; target_low: number | null;
    current_price: number | null;
    distribution: { strongBuy: number; buy: number; hold: number; sell: number; strongSell: number } | null;
  };
};

// Impact materiality: the REAL CO2e of the company's owned power assets, from Climate TRACE.
// The outward half of double materiality (the rating is the inward half). null => N.A.
export type ImpactAsset = {
  name: string | null;
  subsector: string | null;
  country: string | null;
  emissions: number | null;   // tCO2e
};

export type ImpactMateriality = {
  company_id: string;
  owner_id: string | null;
  owner_name: string | null;
  note: string | null;
  year: number;
  gas: string;
  total_emissions_tonnes: number | null;
  asset_count: number;
  top_assets: ImpactAsset[];
  subsector_mix: { subsector: string; emissions: number }[];
  monthly: { month: number; emissions: number }[];
  annual: { year: number; emissions: number }[];
  rank: number | null;
  peers: number | null;
  panel_share: number | null;
  provenance: Provenance | null;
  source: string;
  source_url: string | null;
};

export type RaterKey = "msci" | "sp" | "sustainalytics" | "cdp";

// Where a displayed number came from. "mixed" is the one that matters: a real rating
// blended with a seeded one, which is what made Keppel's old 87.8 divergence misleading.
export type Provenance = "real" | "mixed" | "illustrative";

// A real rating that sits OUTSIDE the analysis year, carried with its own observation
// year rather than re-dated (which would falsify when it was measured).
export type LatestRealRater = {
  rater: RaterKey;
  value: string;
  year: number;
  source: string;
  url: string | null;
  provenance: "real";
};

// CDP listed the company but it did not respond. A disclosure fact, never a score.
export type CdpDisclosure = {
  rater: "cdp";
  status: string | null;
  year: number | null;
  source: string | null;
  url: string | null;
};

export type RaterProvenance = {
  real: boolean;
  source: string | null;
  url: string | null;
  observed_on: string | null;
  value_raw: string | null;
  status?: string | null;                // e.g. "did_not_disclose" — a fact, not a grade
};

export type Raters = {
  company_id: string;
  msci_pct: number | null;
  sp_pct: number | null;
  sustainalytics_pct: number | null;
  cdp_pct: number | null;
  consensus: number | null;
  divergence: number | null;
  consensus_provenance?: Provenance;
  divergence_provenance?: Provenance;
  contributing?: RaterKey[];             // channels that actually fed those two figures
  real_raters?: RaterKey[];              // channels backed by a real rating
  rater_provenance?: Record<RaterKey, RaterProvenance>;
  basis?: string | null;                 // cohort the percentiles are ranked against
  peers?: number | null;
  msci_real?: boolean;
  msci_source?: string | null;
  msci_url?: string | null;
};

export type Signal = {
  company_id: string;
  proof_up: boolean | null;
  opinion_flat: boolean | null;
  price_flat: boolean | null;
  is_underpriced_improver: boolean;
  evidence_pct: number | null;
  evidence_basis: string | null;         // what evidence_pct is relative to
  evidence_peers: number | null;         // size of that cohort
  evidence_gap: number | null;
  momentum: number | null;
  esg_today: number | null;
  quadrant: QuadrantKey | null;
  esg_today_provenance: Provenance | null;
  evidence_gap_provenance: Provenance | null;
  quadrant_provenance: Provenance | null;
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
  source_url?: string | null;
  source_excerpt?: string | null;
  scraped?: boolean;
};

export type Compliance = {
  provenance?: Provenance | null;
  scraped_count?: number;
  counted?: number;
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
  directional_accuracy?: number | null;
  directional_n?: number | null;
  // Which rows `directional_accuracy` was measured on. The training panel is padded with
  // illustrative (seeded) rating targets, so the headline figure is NOT a measurement on
  // published ratings; `accuracy_note` is the qualified sentence and the card shows it
  // verbatim rather than rendering a bare percentage.
  accuracy_basis?: string | null;
  accuracy_note?: string | null;
  real_directional_accuracy?: number | null;
  real_directional_n?: number | null;
  panel_rows?: number | null;
  panel_rows_real?: number | null;
  panel_rows_illustrative?: number | null;
  provenance?: Provenance | null;
  predicted_label?: string | null;
  last_rating_label?: string | null;
  last_rating_year?: number | null;
  direction?: string | null;
  baseline_only?: boolean;
  model_label?: string | null;
  target_year?: number | null;
  drift_years?: number | null;
  drift_note?: string | null;
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
  corroboration_url?: string | null;
  corroboration_source?: string | null;
  satellite?: ClaimSatelliteProof | null;
};

/** Flattened observation attached to a claim that imagery corroborated. */
export type ClaimSatelliteProof = {
  site_id: string;
  site_name: string | null;
  asset_type: string | null;
  lat: number;
  lon: number;
  operator: string | null;
  registry_url: string | null;
  index: string | null;
  change_score: number | null;
  note: string;
  before: SiteScene | null;
  after: SiteScene | null;
  detail_image: string | null;
  detail_attribution: string | null;
  map_links: Record<string, string> | null;
};

export type SiteScene = {
  scene_id: string;
  date: string;
  cloud_cover: number | null;
  image_path: string | null;
};

export type AssetSite = {
  site_id: string;
  company_id: string;
  name: string | null;
  asset_type: string | null;
  lat: number;
  lon: number;
  operator: string | null;
  registry: string;
  registry_url: string | null;
  match_confidence: number;
  footprint: number[][];
};

export type SiteObservation = {
  site: AssetSite;
  before: SiteScene | null;
  after: SiteScene | null;
  index: string | null;
  /** difference-in-differences on that index; null when not measurable */
  change_score: number | null;
  /** true = construction observed, false = not observed, null = inconclusive */
  changed: boolean | null;
  note: string;
  detail_image: string | null;
  detail_attribution: string | null;
  map_links: Record<string, string> | null;
};

export type SatelliteData = {
  company_id: string;
  company: string;
  before_year: number;
  after_year: number;
  /** registry sites found for this company, whether or not imagery has been fetched */
  located: number;
  observations: SiteObservation[];
  disclosure: string;
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

export type CompanyBriefing = {
  id: string;
  headline: string;
  summary: string;
  potentialEffects: string[];
  watchItems: string[];
  sentiment: "positive" | "neutral" | "negative" | "mixed";
  generatedAt: string;
};
export type BriefingOverview = {
  headline: string;
  summary: string;
  watchItems: string[];
  generatedAt: string;
};
export type BriefingData = {
  date: string;
  overview: BriefingOverview | null;
  companies: CompanyBriefing[];
};

export type LiveResearchSource = {
  url: string;
  domain: string;
  source_class: "verified" | "non_verified" | "community";
  title?: string | null;
  snippet?: string | null;
  provider?: string | null;
  fetched_at: string;
};

export type LiveResearchClaim = {
  claim_id: string;
  claim_text: string;
  topic: string;
  verification: "verified" | "non_verified" | "community";
  sentiment: number;
  last_seen: string;
  sources: LiveResearchSource[];
};

export type LiveIntelligence = {
  renewable: {
    company_id: string;
    renewable_status: "Verified" | "Non-verified" | "No evidence found";
    emissions_trend: "Falling" | "Stable" | "Rising" | "No evidence found";
    evidence_count: number;
    verified_count: number;
    latest_evidence_at?: string | null;
    /** Renewable-topic claims found at all — including those that never evidence the
     *  company's OWN consumption, so "none found" can be told apart from "none qualifying". */
    renewable_mentions?: number;
  };
  claims: LiveResearchClaim[];
  community_sentiment_adjustment: number;
  community_sentiment_note: string;
};

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
  rating: RatingScore;
  rating_series: RatingSeriesPoint[];
  impact?: ImpactMateriality | null;
  double_materiality?: DoubleMateriality | null;
  fundamentals?: CompanyFundamentals | null;
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
  peers: { id: string; name: string; evidence_total: number | null; rating_total: number | null }[];
  latest_real_raters?: LatestRealRater[] | null;
  cdp_disclosure?: CdpDisclosure | null;
  benchmark?: IndustryBenchmark | null;
  liveIntelligence?: LiveIntelligence | null;
};

export type IndustryBenchmark = {
  industry: string;
  peers?: number | null;
  total: number | null;
  pillars: { E: number | null; S: number | null; G: number | null };
  source: string | null;                 // null when no bar can be computed or overridden
  is_override: boolean;
};
