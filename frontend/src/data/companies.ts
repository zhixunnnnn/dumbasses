import { useEffect, useState } from "react";
import type { Company } from "../types";
import { palette } from "../theme/tokens";
import { QUADRANT } from "../evidence/lib/ui";
import type { QuadrantKey } from "../evidence/types";
import { RAW_COMPANIES, type RawCompany } from "./realCompanies";

/** The subset of GET /api/companies this module reads. */
type ApiCompanyRow = {
  id: string;
  ticker: string;
  evidence_total: number | null;
  confidence: number | null;
  consensus: number | null;
  divergence: number | null;
  evidence_pct: number | null;
  evidence_basis: string | null;
  evidence_peers: number | null;
  evidence_gap: number | null;
  momentum: number | null;
  quadrant: QuadrantKey | null;
  is_underpriced_improver: boolean;
  compliance_score: number | null;
  forecast: number | null;
  benchmark_total: number | null;
  benchmark_source: string | null;
};

/** "U96.SI" and "U96" both reduce to "U96", which is also the engine id. */
function normalizeTicker(ticker: string): string {
  return ticker.trim().toUpperCase().split(".")[0];
}

/** Joins a public identity row onto its live listing row. Nothing is invented:
 *  a company the engine does not cover keeps nulls all the way to the UI. */
function buildCompany(raw: RawCompany, real: ApiCompanyRow | undefined): Company {
  const quadrant = real?.quadrant ?? null;

  return {
    id: normalizeTicker(raw.t),
    evidenceId: real?.id ?? null,
    name: raw.n,
    ticker: raw.t,
    sector: raw.s,
    region: raw.r,
    domain: raw.web,
    color: quadrant ? QUADRANT[quadrant].color : palette.faint,
    marketCap: raw.cap,
    profile: {
      headquarters: raw.hq,
      business: raw.bio,
      founded: raw.est,
      employees: raw.emp * 1000,
    },
    esgScore: real?.consensus ?? null,
    evidenceScore: real?.evidence_total ?? null,
    evidencePct: real?.evidence_pct ?? null,
    evidenceBasis: real?.evidence_basis ?? null,
    evidencePeers: real?.evidence_peers ?? null,
    evidenceGap: real?.evidence_gap ?? null,
    divergence: real?.divergence ?? null,
    confidence: real?.confidence ?? null,
    momentum: real?.momentum ?? null,
    quadrant,
    isUnderpricedImprover: real?.is_underpriced_improver ?? false,
    complianceScore: real?.compliance_score ?? null,
    forecast: real?.forecast ?? null,
    benchmarkTotal: real?.benchmark_total ?? null,
    benchmarkSource: real?.benchmark_source ?? null,
  };
}

/** Identity-only universe: real names, sectors and regions, no engine figures.
 *  Used where a synchronous lookup is enough (watchlist id validation). */
export const COMPANIES: Company[] = RAW_COMPANIES.map((raw) =>
  buildCompany(raw, undefined),
);

export const COMPANY_BY_ID: Record<string, Company> = Object.fromEntries(
  COMPANIES.map((c) => [c.id, c]),
);

export const SECTOR_LIST = Array.from(
  new Set(COMPANIES.map((c) => c.sector)),
).sort();

export const REGION_LIST = Array.from(
  new Set(COMPANIES.map((c) => c.region)),
).sort();

let companiesPromise: Promise<Company[]> | null = null;

/** Fetch-once join of the identity universe onto the live listing. The two
 *  cover the same ten issuers, so an unmatched ticker is a wiring bug: it is
 *  logged loudly rather than quietly degrading to a scoreless row. */
export function loadCompanies(): Promise<Company[]> {
  if (!companiesPromise) {
    companiesPromise = fetch("/api/companies")
      .then(async (response) => {
        if (!response.ok) throw new Error(`/api/companies → ${response.status}`);
        return (await response.json()) as ApiCompanyRow[];
      })
      .then((rows) => {
        const byTicker = new Map<string, ApiCompanyRow>();
        for (const row of rows) {
          byTicker.set(normalizeTicker(row.id), row);
          byTicker.set(normalizeTicker(row.ticker), row);
        }
        const companies = RAW_COMPANIES.map((raw) =>
          buildCompany(raw, byTicker.get(normalizeTicker(raw.t))),
        );
        const unmatched = companies.filter((c) => c.evidenceId === null);
        if (unmatched.length > 0) {
          console.error(
            "No /api/companies row for:",
            unmatched.map((c) => c.ticker).join(", "),
          );
        }
        return companies;
      })
      .catch((error) => {
        companiesPromise = null;
        throw error;
      });
  }
  return companiesPromise;
}

type CompaniesState = {
  companies: Company[];
  loading: boolean;
  error: string | null;
};

/** Legacy pages read the universe through this hook. Until the listing lands
 *  (or if it fails) the identity-only universe is used, so every engine figure
 *  reads "N.A." instead of a placeholder number. */
export function useCompanies(): CompaniesState {
  const [state, setState] = useState<CompaniesState>({
    companies: COMPANIES,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    loadCompanies()
      .then((companies) => {
        if (!cancelled) setState({ companies, loading: false, error: null });
      })
      .catch((error) => {
        if (!cancelled) {
          setState({
            companies: COMPANIES,
            loading: false,
            error: error instanceof Error ? error.message : "Could not load companies.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
