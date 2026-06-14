import { useMemo, useState } from "react";
import type { Company } from "../../types";
import { COMPANIES } from "../../data/companies";
import { buildIndexCandles, buildStatSeries } from "../../data/market";
import { buildSignalLeaders } from "../../data/signals";
import { QUADRANT_ORDER, QUADRANTS } from "../../lib/quadrant";
import { gradeColor } from "../../theme/tokens";
import { applyFilters, defaultFilters, type Filters } from "../../lib/filters";
import { useNavigation } from "../../navigation/NavigationContext";
import ScatterMatrix from "../scatter/ScatterMatrix";
import { CandlestickChart } from "../charts";
import StatCard from "./StatCard";
import SignalLeaders from "./SignalLeaders";
import FilterPanel from "./FilterPanel";
import SectorLeaderboard from "./SectorLeaderboard";
import RegionBreakdown from "./RegionBreakdown";
import RatingHistogram from "./RatingHistogram";
import ControversyFeed from "./ControversyFeed";
import DeltaBadge from "../common/DeltaBadge";
import Reveal from "../common/Reveal";
import { usePublishAssistantPageContext } from "../chat/PageContext";

const indexCandles = buildIndexCandles();

export default function DashboardPage() {
  const { openCompany } = useNavigation();
  const [filters, setFilters] = useState<Filters>(() =>
    defaultFilters(COMPANIES),
  );

  const filtered = useMemo(() => applyFilters(COMPANIES, filters), [filters]);
  const stats = useMemo(() => buildStatSeries(filtered), [filtered]);
  const leaders = useMemo(() => buildSignalLeaders(filtered, 5), [filtered]);
  const quadrantCounts = useMemo(
    () =>
      QUADRANT_ORDER.map((key) => ({
        key,
        count: filtered.filter((c) => c.quadrant === key).length,
      })),
    [filtered],
  );

  const select = (company: Company) => openCompany(company.id);

  const indexClose = indexCandles[indexCandles.length - 1].close;
  const indexDelta =
    ((indexClose - indexCandles[0].open) / indexCandles[0].open) * 100;
  const pageContext = useMemo(
    () => ({
      route: "dashboard",
      title: "Sustainability Matrix",
      totalCompanies: COMPANIES.length,
      visibleCompanies: filtered.length,
      filters,
      stats: stats.map(({ label, value, delta }) => ({ label, value, delta })),
      quadrantCounts,
      signalLeaders: leaders.map(({ company, insight, delta }) => ({
        name: company.name,
        ticker: company.ticker,
        sector: company.sector,
        region: company.region,
        esgScore: company.esgScore,
        financialScore: company.financialScore,
        insight,
        delta,
      })),
      visibleSample: filtered.slice(0, 12).map(summaryForAssistant),
    }),
    [filtered, filters, leaders, quadrantCounts, stats],
  );
  usePublishAssistantPageContext(pageContext);

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-6 sm:px-8">
      <header className="pb-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
          Q2 2026 · ESG universe
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          Sustainability Matrix
        </h1>
      </header>

      <Reveal>
        <FilterPanel
          companies={COMPANIES}
          filters={filters}
          setFilters={setFilters}
          resultCount={filtered.length}
        />
      </Reveal>

      <Reveal delay={60}>
        <section className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {stats.map((stat) => (
            <StatCard key={stat.id} stat={stat} />
          ))}
        </section>
      </Reveal>

      <section className="mt-5 grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <div className="space-y-5">
          <Reveal delay={120}>
            <div className="rounded-xl border border-hairline bg-surface p-5">
              <div className="mb-1 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">
                    ESG × Financial Performance
                  </h2>
                  <p className="text-sm text-muted">
                    {filtered.length} companies · dot size = market cap
                  </p>
                </div>
              </div>
              <ScatterMatrix
                companies={filtered}
                selectedId={null}
                onSelect={select}
              />
              <Legend />
            </div>
          </Reveal>

          <Reveal delay={160}>
            <div className="rounded-xl border border-hairline bg-surface p-5">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">
                    ESG Composite Index
                  </h2>
                  <p className="text-sm text-muted">20-week price action</p>
                </div>
                <div className="text-right">
                  <p className="font-mono text-lg font-semibold tabular-nums">
                    {indexClose.toFixed(0)}
                  </p>
                  <DeltaBadge delta={indexDelta} />
                </div>
              </div>
              <CandlestickChart candles={indexCandles} />
            </div>
          </Reveal>

          <div className="grid gap-5 sm:grid-cols-2">
            <Reveal delay={200}>
              <SectorLeaderboard companies={filtered} />
            </Reveal>
            <Reveal delay={240}>
              <RatingHistogram companies={filtered} />
            </Reveal>
          </div>
        </div>

        <div className="space-y-5">
          <Reveal delay={120}>
            <SignalLeaders leaders={leaders} onSelect={select} />
          </Reveal>

          <Reveal delay={160}>
            <section className="rounded-xl border border-hairline bg-surface p-5">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
                Quadrant mix
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                {quadrantCounts.map(({ key, count }) => {
                  const meta = QUADRANTS[key];
                  return (
                    <div
                      key={key}
                      className="rounded-lg border border-hairline p-3"
                      style={{ background: `${meta.accent}0e` }}
                    >
                      <div className="flex items-center justify-between">
                        <span
                          className="text-xs font-semibold uppercase tracking-wide"
                          style={{ color: meta.accent }}
                        >
                          {meta.title}
                        </span>
                        <span className="font-mono text-lg font-bold tabular-nums">
                          {count}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] leading-snug text-faint">
                        {meta.blurb}
                      </p>
                    </div>
                  );
                })}
              </div>
            </section>
          </Reveal>

          <Reveal delay={200}>
            <RegionBreakdown companies={filtered} />
          </Reveal>

          <Reveal delay={240}>
            <ControversyFeed companies={filtered} onSelect={select} />
          </Reveal>
        </div>
      </section>

      <footer className="py-8 text-center text-xs text-faint">
        Real companies · illustrative ESG data for demonstration
      </footer>
    </div>
  );
}

function summaryForAssistant(company: Company) {
  return {
    name: company.name,
    ticker: company.ticker,
    sector: company.sector,
    region: company.region,
    grade: company.grade,
    quadrant: company.quadrant,
    esgScore: company.esgScore,
    financialScore: company.financialScore,
    momentum: company.momentum,
    carbonIntensity: company.esgMetrics.carbonIntensity,
    domain: company.domain,
  };
}

function Legend() {
  const grades: [string, string][] = [
    ["AAA–AA", gradeColor.AA],
    ["A–BBB", gradeColor.BBB],
    ["BB–B", gradeColor.B],
    ["CCC", gradeColor.CCC],
  ];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-hairline pt-3 text-xs text-muted">
      <span className="font-medium text-muted">Rating</span>
      {grades.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: color }}
          />
          {label}
        </span>
      ))}
      <span className="ml-auto text-faint">
        Hover a quadrant → zoom → click a dot
      </span>
    </div>
  );
}
