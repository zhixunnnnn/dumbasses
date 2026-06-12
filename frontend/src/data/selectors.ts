import type { Company, Controversy, ESGGrade } from "../types";

const GRADE_ORDER: ESGGrade[] = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"];

export function peersOf(company: Company, all: Company[], n = 5): Company[] {
  return all
    .filter((c) => c.sector === company.sector && c.id !== company.id)
    .sort(
      (a, b) =>
        Math.abs(a.esgScore - company.esgScore) -
        Math.abs(b.esgScore - company.esgScore),
    )
    .slice(0, n);
}

export type SectorStat = {
  sector: string;
  count: number;
  avgEsg: number;
  avgFin: number;
};

export function sectorStats(companies: Company[]): SectorStat[] {
  const map = new Map<string, Company[]>();
  for (const c of companies) {
    const list = map.get(c.sector) ?? [];
    list.push(c);
    map.set(c.sector, list);
  }
  return [...map.entries()]
    .map(([sector, list]) => ({
      sector,
      count: list.length,
      avgEsg: list.reduce((s, c) => s + c.esgScore, 0) / list.length,
      avgFin: list.reduce((s, c) => s + c.financialScore, 0) / list.length,
    }))
    .sort((a, b) => b.avgEsg - a.avgEsg);
}

export type RegionStat = { region: string; count: number; cap: number };

export function regionStats(companies: Company[]): RegionStat[] {
  const map = new Map<string, RegionStat>();
  for (const c of companies) {
    const current = map.get(c.region) ?? { region: c.region, count: 0, cap: 0 };
    current.count += 1;
    current.cap += c.marketCap;
    map.set(c.region, current);
  }
  return [...map.values()].sort((a, b) => b.cap - a.cap);
}

export function gradeDistribution(
  companies: Company[],
): { grade: ESGGrade; count: number }[] {
  return GRADE_ORDER.map((grade) => ({
    grade,
    count: companies.filter((c) => c.grade === grade).length,
  }));
}

export type DatedControversy = Controversy & {
  company: Company;
};

const SEVERITY_WEIGHT = { high: 3, medium: 2, low: 1 } as const;

export function recentControversies(
  companies: Company[],
  n = 6,
): DatedControversy[] {
  return companies
    .flatMap((company) =>
      company.controversies.map((c) => ({ ...c, company })),
    )
    .sort(
      (a, b) =>
        b.year - a.year ||
        SEVERITY_WEIGHT[b.severity] - SEVERITY_WEIGHT[a.severity],
    )
    .slice(0, n);
}

export function sectorPercentile(
  company: Company,
  companies: Company[],
  key: "esgScore" | "financialScore",
): number {
  const peers = companies.filter((c) => c.sector === company.sector);
  if (peers.length <= 1) return 100;
  const below = peers.filter((c) => c[key] <= company[key]).length;
  return Math.round((below / peers.length) * 100);
}
