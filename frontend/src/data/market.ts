import type { Candle, Company, StatSeries } from "../types";
import { round } from "../lib/format";
import { mulberry32 } from "../lib/random";

const WEEKS = [
  "W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08", "W09", "W10",
  "W11", "W12", "W13", "W14", "W15", "W16", "W17", "W18", "W19", "W20",
];

export function buildIndexCandles(): Candle[] {
  const rng = mulberry32(0x5eed01);
  const candles: Candle[] = [];
  let price = 1000;
  for (let i = 0; i < WEEKS.length; i += 1) {
    const open = price;
    const drift = 0.004 + Math.sin(i / 3) * 0.006;
    const close = open * (1 + drift + (rng() - 0.5) * 0.05);
    const wick = open * (0.008 + rng() * 0.02);
    candles.push({
      label: WEEKS[i],
      open: round(open, 1),
      close: round(close, 1),
      high: round(Math.max(open, close) + wick, 1),
      low: round(Math.min(open, close) - wick, 1),
    });
    price = close;
  }
  return candles;
}

function sparkFrom(seed: number, drift: number, points = 24): number[] {
  const rng = mulberry32(seed);
  const out: number[] = [];
  let v = 50;
  for (let i = 0; i < points; i += 1) {
    v = Math.max(2, v * (1 + drift + (rng() - 0.5) * 0.08));
    out.push(round(v, 1));
  }
  return out;
}

export function buildStatSeries(companies: Company[]): StatSeries[] {
  const n = companies.length || 1;
  const avgEsg = companies.reduce((s, c) => s + c.esgScore, 0) / n;
  const totalCap = companies.reduce((s, c) => s + c.marketCap, 0);
  const breadth =
    (companies.filter((c) => c.momentum > 0).length / n) * 100;
  const flags = companies.filter(
    (c) => c.esgMetrics.controversyLevel >= 3,
  ).length;

  return [
    {
      id: "composite",
      label: "ESG composite",
      value: avgEsg.toFixed(1),
      delta: 2.4,
      deviation: 0.61,
      series: sparkFrom(11, 0.004),
    },
    {
      id: "capital",
      label: "Capital screened",
      value: `$${(totalCap / 1000).toFixed(2)}T`,
      delta: 5.1,
      deviation: 1.12,
      series: sparkFrom(22, 0.006),
    },
    {
      id: "breadth",
      label: "Momentum breadth",
      value: `${breadth.toFixed(0)}%`,
      delta: breadth - 50,
      deviation: 2.04,
      series: sparkFrom(33, breadth > 50 ? 0.005 : -0.004),
    },
    {
      id: "flags",
      label: "Controversy flags",
      value: `${flags}`,
      delta: -3.6,
      deviation: 0.88,
      series: sparkFrom(44, -0.006),
    },
  ];
}
