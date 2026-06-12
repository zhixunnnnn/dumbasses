export type ESGGrade = "AAA" | "AA" | "A" | "BBB" | "BB" | "B" | "CCC";

export type QuadrantKey =
  | "leaders"
  | "profitFirst"
  | "purposeFirst"
  | "laggards";

export type Metric = { label: string; value: number };

export type Candle = {
  label: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type Company = {
  id: string;
  name: string;
  ticker: string;
  sector: string;
  region: string;
  domain: string;
  color: string;
  esgScore: number;
  financialScore: number;
  marketCap: number;
  grade: ESGGrade;
  quadrant: QuadrantKey;
  momentum: number;
  deviation: number;
  pillars: {
    environmental: number;
    social: number;
    governance: number;
  };
  financials: {
    revenue: number;
    netIncome: number;
    roe: number;
    profitMargin: number;
    peRatio: number;
    dividendYield: number;
    debtToEquity: number;
    oneYearReturn: number;
  };
  esgMetrics: {
    carbonIntensity: number;
    renewableEnergyPct: number;
    boardIndependencePct: number;
    genderDiversityPct: number;
    employeeTurnover: number;
    controversyLevel: number;
  };
  history: {
    months: string[];
    esgTrend: number[];
    priceTrend: number[];
    emissionsTrend: number[];
    candles: Candle[];
  };
  environmentalBreakdown: Metric[];
  socialBreakdown: Metric[];
  governanceBreakdown: Metric[];
  profile: {
    headquarters: string;
    business: string;
    founded: number;
    employees: number;
  };
  scope: {
    scope1: number;
    scope2: number;
    scope3: number;
  };
  controversies: Controversy[];
};

export type Controversy = {
  title: string;
  severity: "low" | "medium" | "high";
  year: number;
};

export type QuadrantMeta = {
  key: QuadrantKey;
  title: string;
  blurb: string;
  accent: string;
  esgHigh: boolean;
  finHigh: boolean;
};

export type Trend = "up" | "down" | "flat";

export type StatSeries = {
  id: string;
  label: string;
  value: string;
  delta: number;
  deviation: number;
  series: number[];
};

export type SignalLeader = {
  id: string;
  company: Company;
  insight: string;
  delta: number;
  deviation: number;
};
