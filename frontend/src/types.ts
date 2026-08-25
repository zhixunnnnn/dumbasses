import type { QuadrantKey } from "./evidence/types";

export type { QuadrantKey };

/** Public identity joined onto the live engine listing. Every numeric field
 *  below either comes from GET /api/companies or is a published company fact
 *  (market cap, headcount); nothing here is generated client-side. */
export type Company = {
  /** Engine id, e.g. "U96". Also the id used in routes and watchlists. */
  id: string;
  /** Same as `id` when the engine covers the company; null when it does not. */
  evidenceId: string | null;
  name: string;
  ticker: string;
  sector: string;
  region: string;
  domain: string;
  color: string;
  marketCap: number;
  profile: {
    headquarters: string;
    business: string;
    founded: number | null;
    employees: number | null;
  };
  /** Rater consensus percentile. Null = not covered. */
  esgScore: number | null;
  /** Evidence score. Null = not covered. */
  evidenceScore: number | null;
  evidencePct: number | null;
  evidenceBasis: string | null;
  evidencePeers: number | null;
  evidenceGap: number | null;
  divergence: number | null;
  confidence: number | null;
  momentum: number | null;
  quadrant: QuadrantKey | null;
  isUnderpricedImprover: boolean;
  complianceScore: number | null;
  forecast: number | null;
  benchmarkTotal: number | null;
  benchmarkSource: string | null;
};
