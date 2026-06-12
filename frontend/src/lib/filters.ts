import type { Company, ESGGrade, QuadrantKey } from "../types";

export type MomentumFilter = "all" | "positive" | "negative";

export type Filters = {
  search: string;
  sectors: string[];
  regions: string[];
  grades: ESGGrade[];
  quadrants: QuadrantKey[];
  esg: [number, number];
  fin: [number, number];
  cap: [number, number];
  momentum: MomentumFilter;
  maxControversy: number;
  minE: number;
  minS: number;
  minG: number;
};

export function capBounds(companies: Company[]): [number, number] {
  const caps = companies.map((c) => c.marketCap);
  return [Math.floor(Math.min(...caps)), Math.ceil(Math.max(...caps))];
}

export function defaultFilters(companies: Company[]): Filters {
  return {
    search: "",
    sectors: [],
    regions: [],
    grades: [],
    quadrants: [],
    esg: [0, 100],
    fin: [0, 100],
    cap: capBounds(companies),
    momentum: "all",
    maxControversy: 5,
    minE: 0,
    minS: 0,
    minG: 0,
  };
}

export function applyFilters(companies: Company[], f: Filters): Company[] {
  const q = f.search.trim().toLowerCase();
  return companies.filter((c) => {
    if (
      q &&
      !c.name.toLowerCase().includes(q) &&
      !c.ticker.toLowerCase().includes(q)
    )
      return false;
    if (f.sectors.length && !f.sectors.includes(c.sector)) return false;
    if (f.regions.length && !f.regions.includes(c.region)) return false;
    if (f.grades.length && !f.grades.includes(c.grade)) return false;
    if (f.quadrants.length && !f.quadrants.includes(c.quadrant)) return false;
    if (c.esgScore < f.esg[0] || c.esgScore > f.esg[1]) return false;
    if (c.financialScore < f.fin[0] || c.financialScore > f.fin[1])
      return false;
    if (c.marketCap < f.cap[0] || c.marketCap > f.cap[1]) return false;
    if (f.momentum === "positive" && c.momentum < 0) return false;
    if (f.momentum === "negative" && c.momentum >= 0) return false;
    if (c.esgMetrics.controversyLevel > f.maxControversy) return false;
    if (c.pillars.environmental < f.minE) return false;
    if (c.pillars.social < f.minS) return false;
    if (c.pillars.governance < f.minG) return false;
    return true;
  });
}

export function activeFilterCount(f: Filters, base: Filters): number {
  let count = 0;
  if (f.search.trim()) count += 1;
  count += f.sectors.length ? 1 : 0;
  count += f.regions.length ? 1 : 0;
  count += f.grades.length ? 1 : 0;
  count += f.quadrants.length ? 1 : 0;
  if (f.esg[0] !== base.esg[0] || f.esg[1] !== base.esg[1]) count += 1;
  if (f.fin[0] !== base.fin[0] || f.fin[1] !== base.fin[1]) count += 1;
  if (f.cap[0] !== base.cap[0] || f.cap[1] !== base.cap[1]) count += 1;
  if (f.momentum !== "all") count += 1;
  if (f.maxControversy !== base.maxControversy) count += 1;
  if (f.minE || f.minS || f.minG) count += 1;
  return count;
}

export function toggleIn<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}
