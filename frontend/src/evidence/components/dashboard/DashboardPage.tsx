import { api, useApi } from "../../lib/api";
import MomentumMatrix from "./MomentumMatrix";
import ImproverFeed from "./ImproverFeed";
import ScreenerTable from "./ScreenerTable";
import { HypothesisBadge } from "../common/badges";

function Stat({ value, label, accent }: { value: string; label: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-4 py-2.5">
      <p className="text-xl font-semibold" style={{ color: accent }}>{value}</p>
      <p className="text-[11px] text-faint">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const companies = useApi(api.companies, []);
  const matrix = useApi(api.matrix, []);

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

  const rows = companies.data;
  const improvers = rows.filter((r) => r.is_underpriced_improver).length;
  const hidden = rows.filter((r) => r.quadrant === "HIDDEN_WINNERS").length;

  return (
    <div className="mx-auto max-w-[1280px] space-y-5 p-5 md:p-7">
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-pos">
          Singapore · 2019–2023 · evidence over opinion
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-txt">
          Don’t measure ESG. <span className="text-pos">Find what the market mispriced.</span>
        </h1>
        <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted">
          We verify each company’s claims against evidence, surface where the three raters disagree,
          and flag <span className="text-txt">Underpriced Improvers</span> — verified ESG improvement
          the market hasn’t priced yet. Every number traces to a source sentence.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Stat value={`${rows.length}`} label="SG companies screened" />
          <Stat value={`${improvers}`} label="Underpriced Improvers" accent="#3ecf8e" />
          <Stat value={`${hidden}`} label="Hidden Winners" accent="#3ecf8e" />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.7fr_1fr]">
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
          <MomentumMatrix points={matrix.data} />
        </div>
        <ImproverFeed rows={rows} />
      </div>

      <ScreenerTable rows={rows} />
    </div>
  );
}
