import type { Candle, Company, Controversy, Metric } from "../types";
import { gradeColor } from "../theme/tokens";
import { clamp, round } from "../lib/format";
import { hashString, mulberry32, pick, type Rng } from "../lib/random";
import { classifyQuadrant, gradeFromScore } from "../lib/quadrant";
import { RAW_COMPANIES, type RawCompany } from "./realCompanies";

const MONTHS = [
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
];

const CONTROVERSY_POOL: Record<Controversy["severity"], string[]> = {
  high: [
    "Regulatory penalty over disclosure",
    "Major workplace safety incident",
    "Antitrust investigation opened",
    "Environmental remediation order",
  ],
  medium: [
    "Supply-chain labour audit findings",
    "Data privacy enforcement notice",
    "Shareholder governance dispute",
    "Emissions reporting restatement",
  ],
  low: [
    "Minor consumer protection fine",
    "Localized pollution complaint",
    "Executive pay shareholder pushback",
    "Product recall, limited scope",
  ],
};

function buildCandles(rng: Rng, momentum: number): Candle[] {
  const candles: Candle[] = [];
  let price = 100;
  const drift = momentum / 100 / 16;
  for (let i = 0; i < 16; i += 1) {
    const open = price;
    const move = open * (drift + (rng() - 0.5) * 0.06);
    const close = Math.max(5, open + move);
    const wick = open * (0.01 + rng() * 0.03);
    candles.push({
      label: `W${i + 1}`,
      open: round(open, 1),
      close: round(close, 1),
      high: round(Math.max(open, close) + wick, 1),
      low: round(Math.min(open, close) - wick, 1),
    });
    price = close;
  }
  return candles;
}

function buildBreakdown(rng: Rng, base: number, labels: string[]): Metric[] {
  return labels.map((label) => ({
    label,
    value: round(clamp(base + (rng() - 0.5) * 22), 0),
  }));
}

function buildControversies(rng: Rng, level: number): Controversy[] {
  const out: Controversy[] = [];
  const count = Math.min(4, level);
  for (let i = 0; i < count; i += 1) {
    const severity: Controversy["severity"] =
      level >= 4 && i === 0 ? "high" : level >= 3 && i < 2 ? "medium" : "low";
    out.push({
      title: pick(rng, CONTROVERSY_POOL[severity]),
      severity,
      year: 2022 + Math.floor(rng() * 4),
    });
  }
  return out;
}

function buildCompany(raw: RawCompany, index: number): Company {
  const rng = mulberry32(hashString(raw.t + index));
  const jitter = (spread: number) => (rng() - 0.5) * 2 * spread;

  const esgScore = raw.e;
  const financialScore = raw.f;
  const e = esgScore / 100;
  const f = financialScore / 100;
  const marketCap = raw.cap;

  const momentum = round((financialScore - 50) / 50 * 14 + jitter(9), 2);
  const deviation = round(0.8 + rng() * 5.2, 2);

  const environmental = round(clamp(esgScore + jitter(10)), 0);
  const social = round(clamp(esgScore + jitter(9)), 0);
  const governance = round(clamp(esgScore + jitter(11)), 0);

  const financials = {
    revenue: round(marketCap * (0.45 + rng() * 0.7), 1),
    netIncome: round(marketCap * (0.04 + f * 0.09), 2),
    roe: round(6 + f * 22 + jitter(3), 1),
    profitMargin: round(5 + f * 24 + jitter(3), 1),
    peRatio: round(10 + (1 - f) * 18 + rng() * 12, 1),
    dividendYield: round(0.5 + (1 - f) * 3.2 + rng(), 2),
    debtToEquity: round(0.3 + (1 - e) * 1.4 + rng() * 0.4, 2),
    oneYearReturn: round((f - 0.5) * 70 + jitter(12), 1),
  };

  const carbonIntensity = round((1 - e) * 320 + 12 + jitter(20), 0);
  const esgMetrics = {
    carbonIntensity,
    renewableEnergyPct: round(clamp(e * 95 + jitter(8)), 0),
    boardIndependencePct: round(clamp(45 + (governance / 100) * 50 + jitter(5)), 0),
    genderDiversityPct: round(clamp(20 + (social / 100) * 38 + jitter(6)), 0),
    employeeTurnover: round(6 + (1 - social / 100) * 18 + jitter(2), 1),
    controversyLevel: Math.max(
      0,
      Math.min(5, Math.round((1 - e) * 5 + jitter(0.8))),
    ),
  };

  const totalEmissions = round((carbonIntensity * financials.revenue) / 100, 0);
  const scope = {
    scope1: round(totalEmissions * (0.12 + rng() * 0.06), 0),
    scope2: round(totalEmissions * (0.14 + rng() * 0.06), 0),
    scope3: round(totalEmissions * (0.62 + rng() * 0.08), 0),
  };

  const esgTrend: number[] = [];
  const priceTrend: number[] = [];
  const emissionsTrend: number[] = [];
  let price = 100;
  let emissions = carbonIntensity * 1.25;
  for (let i = 0; i < 12; i += 1) {
    const progress = i / 11;
    esgTrend.push(round(clamp(esgScore - 8 + progress * 8 + jitter(2.4)), 1));
    price *= 1 + financials.oneYearReturn / 100 / 11 + jitter(0.025);
    priceTrend.push(round(price, 1));
    emissions *= (1 - (0.01 + e * 0.03)) * (1 + jitter(0.015));
    emissionsTrend.push(round(emissions, 0));
  }

  return {
    id: raw.t.toLowerCase(),
    name: raw.n,
    ticker: raw.t,
    sector: raw.s,
    region: raw.r,
    domain: raw.web,
    color: gradeColor[gradeFromScore(esgScore)],
    esgScore,
    financialScore,
    marketCap,
    grade: gradeFromScore(esgScore),
    quadrant: classifyQuadrant(esgScore, financialScore),
    momentum,
    deviation,
    pillars: { environmental, social, governance },
    financials,
    esgMetrics,
    history: {
      months: MONTHS,
      esgTrend,
      priceTrend,
      emissionsTrend,
      candles: buildCandles(rng, momentum),
    },
    environmentalBreakdown: buildBreakdown(rng, environmental, [
      "Carbon", "Water", "Waste", "Biodiversity",
    ]),
    socialBreakdown: buildBreakdown(rng, social, [
      "Labor", "Safety", "Community", "Privacy",
    ]),
    governanceBreakdown: buildBreakdown(rng, governance, [
      "Board", "Ethics", "Pay", "Transparency",
    ]),
    profile: {
      headquarters: raw.hq,
      business: raw.bio,
      founded: raw.est,
      employees: raw.emp * 1000,
    },
    scope,
    controversies: buildControversies(rng, esgMetrics.controversyLevel),
  };
}

export const COMPANIES: Company[] = RAW_COMPANIES.map(buildCompany);

export const COMPANY_BY_ID: Record<string, Company> = Object.fromEntries(
  COMPANIES.map((c) => [c.id, c]),
);

export const SECTORS = [
  "All sectors",
  ...Array.from(new Set(COMPANIES.map((c) => c.sector))).sort(),
];

export const SECTOR_LIST = Array.from(
  new Set(COMPANIES.map((c) => c.sector)),
).sort();

export const REGION_LIST = Array.from(
  new Set(COMPANIES.map((c) => c.region)),
).sort();
