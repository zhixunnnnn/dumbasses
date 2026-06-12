import type { ESGGrade, QuadrantKey, QuadrantMeta } from "../types";
import { quadrantAccent } from "../theme/tokens";

export const SPLIT = 50;

export const QUADRANTS: Record<QuadrantKey, QuadrantMeta> = {
  leaders: {
    key: "leaders",
    title: "Leaders",
    blurb: "High ESG, strong returns",
    accent: quadrantAccent.leaders,
    esgHigh: true,
    finHigh: true,
  },
  profitFirst: {
    key: "profitFirst",
    title: "Profit-First",
    blurb: "Strong returns, ESG risk",
    accent: quadrantAccent.profitFirst,
    esgHigh: false,
    finHigh: true,
  },
  purposeFirst: {
    key: "purposeFirst",
    title: "Purpose-First",
    blurb: "High ESG, soft returns",
    accent: quadrantAccent.purposeFirst,
    esgHigh: true,
    finHigh: false,
  },
  laggards: {
    key: "laggards",
    title: "Laggards",
    blurb: "Lagging on both axes",
    accent: quadrantAccent.laggards,
    esgHigh: false,
    finHigh: false,
  },
};

export const QUADRANT_ORDER: QuadrantKey[] = [
  "leaders",
  "profitFirst",
  "purposeFirst",
  "laggards",
];

export function classifyQuadrant(esg: number, fin: number): QuadrantKey {
  const highEsg = esg >= SPLIT;
  const highFin = fin >= SPLIT;
  if (highEsg && highFin) return "leaders";
  if (!highEsg && highFin) return "profitFirst";
  if (highEsg && !highFin) return "purposeFirst";
  return "laggards";
}

export function gradeFromScore(score: number): ESGGrade {
  if (score >= 88) return "AAA";
  if (score >= 78) return "AA";
  if (score >= 68) return "A";
  if (score >= 58) return "BBB";
  if (score >= 48) return "BB";
  if (score >= 38) return "B";
  return "CCC";
}

export type DomainBox = { x0: number; x1: number; y0: number; y1: number };

export function quadrantDomain(key: QuadrantKey): DomainBox {
  const meta = QUADRANTS[key];
  return {
    x0: meta.esgHigh ? SPLIT : 0,
    x1: meta.esgHigh ? 100 : SPLIT,
    y0: meta.finHigh ? SPLIT : 0,
    y1: meta.finHigh ? 100 : SPLIT,
  };
}
