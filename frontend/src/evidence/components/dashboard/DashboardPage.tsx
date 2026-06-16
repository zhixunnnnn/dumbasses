import { useMemo, useState } from "react";
import { api, useApi } from "../../lib/api";
import { useNavigation } from "../../navigation/NavigationContext";
import MomentumMatrix from "./MomentumMatrix";
import ImproverFeed from "./ImproverFeed";
import ScreenerTable from "./ScreenerTable";
import { HypothesisBadge } from "../common/badges";
import { FilterBar, applyDashFilters, defaultDashFilters, type DashFilters } from "./Filters";
import { StatRow, SectorLeaderboard, ScoreHistogram, QuadrantMix, ControversyFeed } from "./panels";

export default function DashboardPage() {
  const { openCompany } = useNavigation();
  const companies = useApi(api.companies, []);
  const matrix = useApi(api.matrix, []);
  const news = useApi(api.news, []);
  const [filters, setFilters] = useState<DashFilters>(defaultDashFilters);

  const rows = useMemo(() => companies.data ?? [], [companies.data]);
  const filtered = useMemo(() => applyDashFilters(rows, filters), [rows, filters]);
  const filteredMatrix = useMemo(() => {
    const ids = new Set(filtered.map((r) => r.id));
    return (matrix.data ?? []).filter((p) => ids.has(p.id));
  }, [matrix.data, filtered]);

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
    <div className="mx-auto max-w-[1320px] space-y-5 p-5 md:p-7">
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-pos">
          Singapore · 2019–2023 · evidence over opinion
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-txt">
          Don’t measure ESG. <span className="text-pos">Find what the market mispriced.</span>
        </h1>
        <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted">
          We verify each company’s claims against evidence, surface where the three raters disagree, and
          flag <span className="text-txt">Underpriced Improvers</span> — verified ESG improvement the market
          hasn’t priced yet. Every number traces to a source sentence.
        </p>
      </header>

      <FilterBar rows={rows} filters={filters} setFilters={setFilters} resultCount={filtered.length} />

      <StatRow rows={filtered} news={news.data} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.7fr_1fr]">
        <div className="space-y-5">
          <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
            <div className="mb-1 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-txt">ESG Momentum Matrix</h3>
                <p className="text-[11px] text-faint">
                  Where the market rates them today × where the evidence is heading. Click a point.
                </p>
              </div>
              <HypothesisBadge note="That improvers outperform is the thesis under test — not yet backtested on this set." />
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
  );
}
