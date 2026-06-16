import { ArrowRight, BookMarked, Trash2 } from "lucide-react";
import { useMemo } from "react";
import type { Company } from "../../types";
import { sectorStats } from "../../data/selectors";
import { QUADRANTS } from "../../lib/quadrant";
import { usdBillions } from "../../lib/format";
import { gradeColor } from "../../theme/tokens";
import { useNavigation } from "../../navigation/NavigationContext";
import CompanyLogo from "../common/CompanyLogo";
import DeltaBadge from "../common/DeltaBadge";
import Reveal from "../common/Reveal";
import { usePublishAssistantPageContext } from "../chat/PageContext";
import { useWatchlist } from "./WatchlistContext";

export default function WatchlistsPage() {
  const { navigate, openCompany } = useNavigation();
  const { watchlistCompanies, removeFromWatchlist, clearWatchlist } =
    useWatchlist();

  const stats = useMemo(() => buildWatchlistStats(watchlistCompanies), [
    watchlistCompanies,
  ]);

  const pageContext = useMemo(
    () => ({
      route: "watchlists",
      title: "Watchlists",
      watchlistCount: watchlistCompanies.length,
      summary: stats,
      watchlistCompanies: watchlistCompanies.map(summaryForAssistant),
    }),
    [stats, watchlistCompanies],
  );
  usePublishAssistantPageContext(pageContext);

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-6 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4 pb-5">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Saved coverage
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Watchlists
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Track selected companies from Explore and keep the agent aware
            of the names you care about.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {watchlistCompanies.length > 0 && (
            <button
              onClick={clearWatchlist}
              className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-surface px-3 py-2 text-sm font-medium text-muted transition hover:bg-raised hover:text-txt"
            >
              <Trash2 size={15} />
              Clear
            </button>
          )}
          <button
            onClick={() => navigate({ name: "explore" })}
            className="inline-flex items-center gap-2 rounded-lg bg-pos px-3 py-2 text-sm font-semibold text-canvas transition hover:opacity-90"
          >
            Add from Explore
            <ArrowRight size={15} />
          </button>
        </div>
      </header>

      <Reveal>
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Companies" value={`${watchlistCompanies.length}`} />
          <StatCard label="Average ESG" value={formatScore(stats.averageEsg)} />
          <StatCard
            label="Average financial"
            value={formatScore(stats.averageFinancial)}
          />
          <StatCard label="Market cap" value={usdBillions(stats.marketCap)} />
        </section>
      </Reveal>

      {watchlistCompanies.length === 0 ? (
        <Reveal delay={80}>
          <section className="mt-5 rounded-2xl border border-dashed border-hairline bg-surface p-10 text-center shadow-panel">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-pos/15 text-pos">
              <BookMarked size={22} />
            </div>
            <h2 className="mt-4 text-lg font-semibold">No companies saved yet</h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted">
              Use Explore to add companies. They will appear here and become
              part of the agent page context.
            </p>
            <button
              onClick={() => navigate({ name: "explore" })}
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-pos px-4 py-2 text-sm font-semibold text-canvas transition hover:opacity-90"
            >
              Open Explore
              <ArrowRight size={15} />
            </button>
          </section>
        </Reveal>
      ) : (
        <div className="mt-5 grid gap-5 xl:grid-cols-[1.45fr_0.85fr]">
          <section className="space-y-3">
            {watchlistCompanies.map((company, index) => (
              <Reveal key={company.id} delay={Math.min(200, index * 25)}>
                <WatchlistCompanyCard
                  company={company}
                  onOpen={() => openCompany(company.id)}
                  onRemove={() => removeFromWatchlist(company.id)}
                />
              </Reveal>
            ))}
          </section>

          <aside className="space-y-5">
            <Reveal delay={80}>
              <Panel title="Sector exposure">
                <ul className="space-y-3">
                  {stats.sectors.map((sector) => (
                    <li key={sector.sector}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="truncate text-muted">
                          {sector.sector}
                        </span>
                        <span className="font-mono text-txt">
                          {sector.count}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-raised">
                        <div
                          className="h-full rounded-full bg-pos/75"
                          style={{
                            width: `${Math.max(
                              8,
                              (sector.count / watchlistCompanies.length) * 100,
                            )}%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </Panel>
            </Reveal>

            <Reveal delay={120}>
              <Panel title="Agent context">
                <p className="text-sm leading-relaxed text-muted">
                  The full-page agent and floating chat receive this
                  watchlist as page context, so questions can reference saved
                  companies, sectors, scores, and risk signals directly.
                </p>
              </Panel>
            </Reveal>
          </aside>
        </div>
      )}
    </div>
  );
}

function WatchlistCompanyCard({
  company,
  onOpen,
  onRemove,
}: {
  company: Company;
  onOpen: () => void;
  onRemove: () => void;
}) {
  const quadrant = QUADRANTS[company.quadrant];

  return (
    <article className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <button
          onClick={onOpen}
          className="flex min-w-0 flex-1 items-start gap-3 text-left transition hover:opacity-85"
        >
          <CompanyLogo company={company} size={44} radius={12} />
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
          </span>
        </button>

        <button
          onClick={onRemove}
          className="inline-flex items-center gap-1.5 rounded-lg border border-hairline bg-canvas px-3 py-2 text-xs font-semibold text-muted transition hover:bg-neg/10 hover:text-neg"
        >
          <Trash2 size={14} />
          Remove
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
        <Metric label="ESG" value={`${company.esgScore}`} />
        <Metric label="Financial" value={`${company.financialScore}`} />
        <Metric label="Grade" value={company.grade} color={gradeColor[company.grade]} />
        <Metric label="Market cap" value={usdBillions(company.marketCap)} />
        <Metric label="Momentum" value={<DeltaBadge delta={company.momentum} align="left" />} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
        <span
          className="rounded-md px-2 py-1 text-xs font-semibold"
          style={{ background: `${quadrant.accent}1f`, color: quadrant.accent }}
        >
          {quadrant.title} - {quadrant.blurb}
        </span>
        <button
          onClick={onOpen}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-txt"
        >
          Open company
          <ArrowRight size={13} />
        </button>
      </div>
    </article>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5 shadow-panel">
      <p className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-faint">
        {title}
      </p>
      {children}
    </section>
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

function Metric({
  label,
  value,
  color,
}: {
  label: string;
  value: string | React.ReactNode;
  color?: string;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas/55 p-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-faint">
        {label}
      </p>
      <div
        className="mt-1 font-mono text-sm font-semibold tabular-nums text-txt"
        style={color ? { color } : undefined}
      >
        {value}
      </div>
    </div>
  );
}

function buildWatchlistStats(companies: Company[]) {
  const averageEsg = average(companies.map((company) => company.esgScore));
  const averageFinancial = average(
    companies.map((company) => company.financialScore),
  );
  const marketCap = companies.reduce(
    (sum, company) => sum + company.marketCap,
    0,
  );

  return {
    averageEsg,
    averageFinancial,
    marketCap,
    sectors: sectorStats(companies),
  };
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
    grade: company.grade,
    quadrant: company.quadrant,
    esgScore: company.esgScore,
    financialScore: company.financialScore,
    momentum: company.momentum,
    marketCap: company.marketCap,
    carbonIntensity: company.esgMetrics.carbonIntensity,
    controversyLevel: company.esgMetrics.controversyLevel,
    domain: company.domain,
  };
}
