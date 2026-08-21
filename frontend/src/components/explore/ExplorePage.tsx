import {
  BookMarked,
  Check,
  ExternalLink,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import type { Company } from "../../types";
import { REGION_LIST, SECTOR_LIST, useCompanies } from "../../data/companies";
import { QUADRANT } from "../../evidence/lib/ui";
import { usdBillions } from "../../lib/format";
import { useNavigation } from "../../navigation/NavigationContext";
import CompanyLogo from "../common/CompanyLogo";
import DeltaBadge from "../common/DeltaBadge";
import Reveal from "../common/Reveal";
import { usePublishAssistantPageContext } from "../chat/PageContext";
import { useWatchlist } from "../watchlist/WatchlistContext";

type SortKey =
  | "esg-desc"
  | "evidence-desc"
  | "momentum-desc"
  | "market-cap-desc"
  | "name-asc";

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "esg-desc", label: "ESG consensus" },
  { key: "evidence-desc", label: "Evidence score" },
  { key: "momentum-desc", label: "Momentum" },
  { key: "market-cap-desc", label: "Market cap" },
  { key: "name-asc", label: "Company name" },
];

const ALL_SECTORS = "All sectors";
const ALL_REGIONS = "All regions";

export default function ExplorePage() {
  const { companies, error } = useCompanies();
  const { navigate, openCompany } = useNavigation();
  const {
    watchlistCompanies,
    addToWatchlist,
    removeFromWatchlist,
    isWatchlisted,
  } = useWatchlist();
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState(ALL_SECTORS);
  const [region, setRegion] = useState(ALL_REGIONS);
  const [sort, setSort] = useState<SortKey>("esg-desc");
  const deferredQuery = useDeferredValue(query);

  const filteredCompanies = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();
    return [...companies]
      .filter((company) => {
        const matchesQuery =
          !needle ||
          [
            company.name,
            company.ticker,
            company.sector,
            company.region,
            company.profile.headquarters,
          ]
            .join(" ")
            .toLowerCase()
            .includes(needle);
        const matchesSector = sector === ALL_SECTORS || company.sector === sector;
        const matchesRegion = region === ALL_REGIONS || company.region === region;
        return matchesQuery && matchesSector && matchesRegion;
      })
      .sort((a, b) => sortCompanies(a, b, sort));
  }, [companies, deferredQuery, region, sector, sort]);

  const summary = useMemo(() => {
    const avgEsg = average(
      filteredCompanies
        .map((company) => company.esgScore)
        .filter((value): value is number => value !== null),
    );
    const avgEvidence = average(
      filteredCompanies
        .map((company) => company.evidenceScore)
        .filter((value): value is number => value !== null),
    );
    const improvers = filteredCompanies.filter(
      (company) => company.isUnderpricedImprover,
    ).length;
    return { avgEsg, avgEvidence, improvers };
  }, [filteredCompanies]);

  const pageContext = useMemo(
    () => ({
      route: "explore",
      title: "Explore ESG universe",
      filters: { query, sector, region, sort },
      totalCompanies: companies.length,
      visibleCompanies: filteredCompanies.length,
      visibleSample: filteredCompanies.slice(0, 20).map(summaryForAssistant),
      watchlistCount: watchlistCompanies.length,
      watchlistCompanies: watchlistCompanies.map(summaryForAssistant),
    }),
    [companies, filteredCompanies, query, region, sector, sort, watchlistCompanies],
  );
  usePublishAssistantPageContext(pageContext);

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-6 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4 pb-5">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Company discovery
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Explore ESG Universe
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Search the full coverage universe, compare the engine's consensus
            and evidence signals, and add companies to your watchlist for
            deeper tracking.
          </p>
        </div>
        <button
          onClick={() => navigate({ name: "watchlists" })}
          className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-surface px-3 py-2 text-sm font-medium text-txt shadow-panel transition hover:bg-raised"
        >
          <BookMarked size={16} />
          Watchlist
          <span className="rounded-md bg-pos/15 px-1.5 py-0.5 font-mono text-xs text-pos">
            {watchlistCompanies.length}
          </span>
        </button>
      </header>

      {error && (
        <p className="mb-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      <Reveal>
        <section className="rounded-2xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
            <SlidersHorizontal size={14} />
            Discovery controls
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
            <label className="relative">
              <Search
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search company, ticker, sector, region..."
                className="h-11 w-full rounded-lg border border-hairline bg-canvas pl-9 pr-3 text-sm outline-none transition placeholder:text-faint focus:border-pos/60"
              />
            </label>
            <Select
              label="Sector"
              value={sector}
              onChange={setSector}
              options={[ALL_SECTORS, ...SECTOR_LIST]}
            />
            <Select
              label="Region"
              value={region}
              onChange={setRegion}
              options={[ALL_REGIONS, ...REGION_LIST]}
            />
            <Select
              label="Sort by"
              value={sort}
              onChange={(value) => setSort(value as SortKey)}
              options={SORT_OPTIONS.map((option) => option.key)}
              labels={Object.fromEntries(
                SORT_OPTIONS.map((option) => [option.key, option.label]),
              )}
            />
          </div>
        </section>
      </Reveal>

      <Reveal delay={60}>
        <section className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Visible companies" value={`${filteredCompanies.length}`} />
          <StatCard label="Average ESG consensus" value={formatScore(summary.avgEsg)} />
          <StatCard
            label="Average evidence score"
            value={formatScore(summary.avgEvidence)}
          />
          <StatCard
            label="Underpriced improvers"
            value={`${summary.improvers}`}
          />
        </section>
      </Reveal>

      <section className="mt-5 grid gap-3 xl:grid-cols-2">
        {filteredCompanies.map((company, index) => (
          <Reveal key={company.id} delay={Math.min(220, index * 18)}>
            <CompanyResultCard
              company={company}
              inWatchlist={isWatchlisted(company.id)}
              onOpen={() => openCompany(company.id)}
              onToggle={() =>
                isWatchlisted(company.id)
                  ? removeFromWatchlist(company.id)
                  : addToWatchlist(company.id)
              }
            />
          </Reveal>
        ))}
      </section>

      {filteredCompanies.length === 0 && (
        <div className="mt-5 rounded-xl border border-hairline bg-surface p-8 text-center">
          <p className="font-semibold text-txt">No companies match this view.</p>
          <p className="mt-1 text-sm text-muted">
            Clear the search or broaden the sector and region filters.
          </p>
        </div>
      )}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  labels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-lg border border-hairline bg-canvas px-3 text-sm outline-none transition focus:border-pos/60"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {labels?.[option] ?? option}
          </option>
        ))}
      </select>
    </label>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
        {label}
      </p>
      <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-txt">
        {value}
      </p>
    </div>
  );
}

function CompanyResultCard({
  company,
  inWatchlist,
  onOpen,
  onToggle,
}: {
  company: Company;
  inWatchlist: boolean;
  onOpen: () => void;
  onToggle: () => void;
}) {
  const quadrant = company.quadrant ? QUADRANT[company.quadrant] : null;

  return (
    <article className="group rounded-xl border border-hairline bg-surface p-4 shadow-panel transition hover:-translate-y-0.5 hover:border-pos/35 hover:bg-raised/40">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <button
          onClick={onOpen}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <CompanyLogo company={company} size={42} radius={12} />
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <span className="truncate text-base font-semibold text-txt">
                {company.name}
              </span>
              <span className="font-mono text-xs text-faint">
                {company.ticker}
              </span>
            </span>
            <span className="mt-1 block text-sm text-muted">
              {company.sector} - {company.region}
            </span>
            <span className="mt-1 block line-clamp-2 text-xs leading-snug text-faint">
              {company.profile.business}
            </span>
          </span>
        </button>

        <button
          onClick={onToggle}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition ${
            inWatchlist
              ? "bg-pos/15 text-pos hover:bg-pos/20"
              : "border border-hairline bg-canvas text-muted hover:bg-raised hover:text-txt"
          }`}
        >
          {inWatchlist ? <Check size={14} /> : <BookMarked size={14} />}
          {inWatchlist ? "Saved" : "Add"}
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="ESG consensus" value={formatValue(company.esgScore)} />
        <Metric label="Evidence" value={formatValue(company.evidenceScore)} />
        <Metric label="Market cap" value={usdBillions(company.marketCap)} />
        <Metric
          label="Momentum"
          value={
            company.momentum === null ? (
              "N.A."
            ) : (
              <DeltaBadge delta={company.momentum} align="left" />
            )
          }
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
        <div className="flex flex-wrap items-center gap-2">
          {quadrant ? (
            <span
              className="rounded-md px-2 py-1 text-xs font-semibold"
              style={{ background: `${quadrant.color}1f`, color: quadrant.color }}
            >
              {quadrant.label}
            </span>
          ) : (
            <span className="rounded-md px-2 py-1 text-xs font-semibold text-faint">
              Not placed by the engine
            </span>
          )}
        </div>
        <button
          onClick={onOpen}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-txt"
        >
          Open company
          <ExternalLink size={13} />
        </button>
      </div>
    </article>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas/55 p-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <div className="mt-1 font-mono text-sm font-semibold tabular-nums text-txt">
        {value}
      </div>
    </div>
  );
}

function sortCompanies(a: Company, b: Company, sort: SortKey) {
  switch (sort) {
    case "evidence-desc":
      return nullsLast(a.evidenceScore, b.evidenceScore);
    case "momentum-desc":
      return nullsLast(a.momentum, b.momentum);
    case "market-cap-desc":
      return b.marketCap - a.marketCap;
    case "name-asc":
      return a.name.localeCompare(b.name);
    case "esg-desc":
    default:
      return nullsLast(a.esgScore, b.esgScore);
  }
}

/** Descending, but an absent figure sorts last rather than as a zero. */
function nullsLast(a: number | null, b: number | null) {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

function formatValue(value: number | null) {
  return value === null ? "N.A." : `${Math.round(value)}`;
}

function average(values: number[]) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatScore(value: number) {
  return value ? value.toFixed(1) : "-";
}

function summaryForAssistant(company: Company) {
  return {
    name: company.name,
    ticker: company.ticker,
    sector: company.sector,
    region: company.region,
    quadrant: company.quadrant,
    esgConsensus: company.esgScore,
    evidenceScore: company.evidenceScore,
    evidenceBasis: company.evidenceBasis,
    divergence: company.divergence,
    confidence: company.confidence,
    momentum: company.momentum,
    marketCap: company.marketCap,
    complianceScore: company.complianceScore,
    isUnderpricedImprover: company.isUnderpricedImprover,
    domain: company.domain,
  };
}
