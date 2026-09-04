import { useMemo, useState } from "react";
import { api, useApi } from "../../lib/api";
import { useNavigation } from "../../navigation/NavigationContext";
import MomentumMatrix from "./MomentumMatrix";
import { BriefingFeed, BriefingOverview } from "./MondayBriefing";
import ImproverFeed from "./ImproverFeed";
import ScreenerTable from "./ScreenerTable";
import { HypothesisBadge } from "../common/badges";
import { FilterBar, applyDashFilters, defaultDashFilters, type DashFilters } from "./Filters";
import { StatRow, SectorLeaderboard, ScoreHistogram, QuadrantMix, ControversyFeed } from "./panels";
import { usePublishAssistantPageContext } from "../../../components/chat/PageContext";

export default function DashboardPage() {
  const { openCompany } = useNavigation();
  const companies = useApi(api.companies, []);
  const matrix = useApi(api.matrix, []);
  const news = useApi(api.news, []);
  const briefing = useApi(api.briefing, []);
  const [filters, setFilters] = useState<DashFilters>(defaultDashFilters);

  const rows = useMemo(() => companies.data ?? [], [companies.data]);
  const filtered = useMemo(() => applyDashFilters(rows, filters), [rows, filters]);
  const filteredMatrix = useMemo(() => {
    const ids = new Set(filtered.map((r) => r.id));
    return (matrix.data ?? []).filter((p) => ids.has(p.id));
  }, [matrix.data, filtered]);
  const pageContext = useMemo(() => ({
    route: "dashboard",
    title: "ASEAN Utilities ESG Terminal",
    scope: "10 ASEAN-listed power, energy & utilities companies",
    filters,
    companies: filtered.map((row) => ({
      id: row.id,
      name: row.name,
      ticker: row.ticker,
      sector: row.sector,
      esgRating: row.rating_total,
      evidenceScore: row.evidence_total,
      confidence: row.confidence,
      consensus: row.consensus,
      divergence: row.divergence,
      evidenceGap: row.evidence_gap,
      momentum: row.momentum,
      quadrant: row.quadrant,
      underpricedImprover: row.is_underpriced_improver,
      complianceScore: row.compliance_score,
      forecast: row.forecast,
    })),
    liveNews: news.data?.companies.map((company) => ({
      id: company.company_id,
      name: company.name,
      sentiment: company.sentiment,
      controversy: company.controversy,
      positive: company.positive,
      headlines: company.headlines.slice(0, 3),
    })) ?? [],
  }), [filtered, filters, news.data]);
  usePublishAssistantPageContext(pageContext);

  if (companies.loading || matrix.loading)
    return <div className="p-10 text-sm text-muted">Loading the evidence engine…</div>;
  if (companies.error || !companies.data || !matrix.data)
    return (
      <div className="p-10 text-sm text-neg">
        Couldn’t reach the engine API. Start the backend:{" "}
        <code className="text-muted">uvicorn backend.app.main:app</code>
        <p className="mt-1 text-faint">{companies.error}</p>
      </div>
    );

  return (
    <div className="mx-auto max-w-[1680px] space-y-5 p-5 md:p-7">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-txt">
          Don’t measure ESG. <span className="text-pos">Find what the market mispriced.</span>
        </h1>
        <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted">
          We verify each company’s claims against evidence, surface where the three raters disagree, and
          flag <span className="text-txt">Underpriced Improvers</span> — verified ESG improvement the market
          hasn’t priced yet. Every number traces to a source sentence.
        </p>
      </header>

      <BriefingOverview state={briefing} />

      {/* Dashboard body, with the per-company briefing pinned as its own far-right rail. */}
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
        <div className="min-w-0 space-y-5">
          <FilterBar rows={rows} filters={filters} setFilters={setFilters} resultCount={filtered.length} />

          <StatRow rows={filtered} news={news.data} />

          <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.7fr_1fr]">
            <div className="space-y-5">
              <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
                <div className="mb-1 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-txt">ESG rating × emission momentum</h3>
                    <p className="text-[11px] text-faint">
                      The ESG rating (x) against where real emissions are heading (y). Top-right = rated well and decarbonising; bottom-right = rated well but emissions rising. Click a point.
                    </p>
                  </div>
                  <HypothesisBadge note="Whether decarbonising names outperform is a thesis under test — not yet backtested on this set." />
                </div>
                <MomentumMatrix points={filteredMatrix} />
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                <ScoreHistogram rows={filtered} />
                <SectorLeaderboard rows={filtered} />
              </div>
            </div>

            <div className="space-y-5">
              <ImproverFeed rows={filtered} />
              <QuadrantMix rows={filtered} />
              <ControversyFeed rows={filtered} news={news.data} onSelect={openCompany} />
            </div>
          </div>

          <ScreenerTable rows={filtered} />
        </div>

        {/* Below xl the rail stacks; keep it next to the overview instead of below the screener. */}
        <aside className="order-first xl:order-none xl:sticky xl:top-5 xl:max-h-[calc(100dvh-2.5rem)] xl:overflow-y-auto">
          <BriefingFeed state={briefing} onSelect={openCompany}
            ratingById={new Map(filtered.map((r) => [r.id, r.rating_total]))} />
        </aside>
      </div>
    </div>
  );
}
