import type { Company, SignalLeader } from "../types";

function insightFor(company: Company): string {
  const { pillars, esgMetrics } = company;
  const best = Math.max(
    pillars.environmental,
    pillars.social,
    pillars.governance,
  );
  if (best === pillars.environmental) {
    return `cut carbon intensity to ${esgMetrics.carbonIntensity} tCO₂e per $M`;
  }
  if (best === pillars.governance) {
    return `lifted board independence to ${esgMetrics.boardIndependencePct}%`;
  }
  return `improved workforce diversity to ${esgMetrics.genderDiversityPct}%`;
}

export function buildSignalLeaders(
  companies: Company[],
  limit = 5,
): SignalLeader[] {
  return [...companies]
    .sort((a, b) => b.momentum - a.momentum)
    .slice(0, limit)
    .map((company) => ({
      id: company.id,
      company,
      insight: insightFor(company),
      delta: company.momentum,
      deviation: company.deviation,
    }));
}
