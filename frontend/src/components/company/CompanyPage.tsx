import { useState } from "react";
import {
  ArrowLeft,
  AlertTriangle,
  Building2,
  Users,
  CalendarDays,
  MapPin,
} from "lucide-react";
import type { Company, Controversy } from "../../types";
import { COMPANIES, COMPANY_BY_ID } from "../../data/companies";
import { peersOf, sectorPercentile } from "../../data/selectors";
import { QUADRANTS } from "../../lib/quadrant";
import { gradeColor, pillarColor } from "../../theme/tokens";
import { compact, signedPercent, usdBillions } from "../../lib/format";
import { useNavigation } from "../../navigation/NavigationContext";
import {
  BarChart,
  CandlestickChart,
  Donut,
  Gauge,
  LineChart,
  RadarChart,
} from "../charts";
import DeltaBadge from "../common/DeltaBadge";
import CompanyLogo from "../common/CompanyLogo";
import Reveal from "../common/Reveal";

const TREND_TABS = [
  { key: "candles", label: "Price action" },
  { key: "esg", label: "ESG score" },
  { key: "emissions", label: "Emissions" },
] as const;

type TrendKey = (typeof TREND_TABS)[number]["key"];

export default function CompanyPage({ id }: { id: string }) {
  const company = COMPANY_BY_ID[id];
  const { goBack, openCompany } = useNavigation();
  const [trend, setTrend] = useState<TrendKey>("candles");

  if (!company) {
    return (
      <div className="p-8 text-muted">
        Company not found.{" "}
        <button onClick={goBack} className="text-pos underline">
          Go back
        </button>
      </div>
    );
  }

  const meta = QUADRANTS[company.quadrant];
  const fin = company.financials;
  const esg = company.esgMetrics;
  const peers = peersOf(company, COMPANIES);
  const esgPct = sectorPercentile(company, COMPANIES, "esgScore");
  const finPct = sectorPercentile(company, COMPANIES, "financialScore");
  const positiveReturn = fin.oneYearReturn >= 0;

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-6 sm:px-8">
      <button
        onClick={goBack}
        className="mb-5 flex items-center gap-2 text-sm text-muted transition hover:text-txt"
      >
        <ArrowLeft size={16} /> Back to matrix
      </button>

      <div
        className="overflow-hidden rounded-2xl border border-hairline"
        style={{
          background: `linear-gradient(135deg, ${meta.accent}1f, ${company.color}0d 60%, transparent)`,
          animation: "scale-in 0.5s cubic-bezier(0.22,1,0.36,1) both",
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-5 p-6">
          <div className="flex items-start gap-4">
            <CompanyLogo company={company} size={64} radius={16} />
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl font-semibold tracking-tight">
                  {company.name}
                </h1>
                <span className="font-mono text-sm text-muted">
                  {company.ticker}
                </span>
              </div>
              <p className="mt-1 max-w-xl text-sm text-muted">
                {company.profile.business}
              </p>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-faint">
                <span className="flex items-center gap-1.5">
                  <Building2 size={13} /> {company.sector}
                </span>
                <span className="flex items-center gap-1.5">
                  <MapPin size={13} /> {company.profile.headquarters}
                </span>
                <span className="flex items-center gap-1.5">
                  <CalendarDays size={13} /> Founded {company.profile.founded}
                </span>
                <span className="flex items-center gap-1.5">
                  <Users size={13} /> {compact(company.profile.employees)}{" "}
                  employees
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <span
                className="rounded-lg px-3 py-1.5 text-base font-bold text-canvas"
                style={{ background: gradeColor[company.grade] }}
              >
                {company.grade}
              </span>
              <span
                className="rounded-lg px-3 py-1.5 text-sm font-semibold"
                style={{ background: `${meta.accent}22`, color: meta.accent }}
              >
                {meta.title}
              </span>
            </div>
            <DeltaBadge delta={company.momentum} deviation={company.deviation} />
          </div>
        </div>
      </div>

      <Reveal delay={60}>
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi label="ESG score" value={`${company.esgScore}`} />
          <Kpi label="Financial" value={`${company.financialScore}`} />
          <Kpi label="Market cap" value={usdBillions(company.marketCap)} />
          <Kpi label="Revenue" value={usdBillions(fin.revenue)} />
          <Kpi
            label="1Y return"
            value={signedPercent(fin.oneYearReturn, 1)}
            tone={positiveReturn ? "pos" : "neg"}
          />
          <Kpi label="P/E" value={`${fin.peRatio}`} />
        </div>
      </Reveal>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Reveal delay={120} className="lg:col-span-2">
          <Panel>
            <div className="mb-3 flex items-center justify-between">
              <SectionTitle>Performance</SectionTitle>
              <div className="inline-flex rounded-lg border border-hairline bg-canvas p-0.5">
                {TREND_TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTrend(t.key)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                      trend === t.key
                        ? "bg-raised text-txt"
                        : "text-muted hover:text-txt"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            {trend === "candles" && (
              <CandlestickChart candles={company.history.candles} height={260} />
            )}
            {trend === "esg" && (
              <LineChart
                data={company.history.esgTrend}
                labels={company.history.months}
                color={pillarColor.environmental}
                height={260}
              />
            )}
            {trend === "emissions" && (
              <LineChart
                data={company.history.emissionsTrend}
                labels={company.history.months}
                color="#ec6a5e"
                valueSuffix="t"
                height={260}
              />
            )}
          </Panel>
        </Reveal>

        <Reveal delay={180}>
          <Panel>
            <SectionTitle>ESG pillars</SectionTitle>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Gauge value={company.pillars.environmental} label="Environment" color={pillarColor.environmental} />
              <Gauge value={company.pillars.social} label="Social" color={pillarColor.social} />
              <Gauge value={company.pillars.governance} label="Governance" color={pillarColor.governance} />
            </div>
            <div className="mt-4 space-y-2 border-t border-hairline pt-4">
              <PercentileBar label="ESG vs sector" value={esgPct} color={pillarColor.environmental} />
              <PercentileBar label="Financial vs sector" value={finPct} color={pillarColor.social} />
            </div>
          </Panel>
        </Reveal>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Reveal delay={120}>
          <Panel>
            <SectionTitle>Pillar radar</SectionTitle>
            <RadarChart
              data={[
                { label: "Env", value: company.pillars.environmental },
                { label: "Soc", value: company.pillars.social },
                { label: "Gov", value: company.pillars.governance },
                { label: "Carbon", value: company.environmentalBreakdown[0].value },
                { label: "Board", value: company.governanceBreakdown[0].value },
                { label: "Labor", value: company.socialBreakdown[0].value },
              ]}
              color={meta.accent}
            />
          </Panel>
        </Reveal>

        <Reveal delay={160}>
          <Panel>
            <SectionTitle>Emissions by scope</SectionTitle>
            <p className="mb-3 mt-1 text-xs text-faint">
              ktCO₂e · modelled estimate
            </p>
            <Donut
              segments={[
                { label: "Scope 1 (direct)", value: company.scope.scope1, color: "#ec6a5e" },
                { label: "Scope 2 (energy)", value: company.scope.scope2, color: "#e0b24a" },
                { label: "Scope 3 (value chain)", value: company.scope.scope3, color: "#4cc4d4" },
              ]}
              centerValue={compact(
                company.scope.scope1 + company.scope.scope2 + company.scope.scope3,
              )}
              centerLabel="total"
            />
          </Panel>
        </Reveal>

        <Reveal delay={200}>
          <Panel>
            <SectionTitle>Environmental sub-scores</SectionTitle>
            <div className="mt-3">
              <BarChart data={company.environmentalBreakdown} height={170} />
            </div>
          </Panel>
        </Reveal>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Reveal delay={120}>
          <Panel>
            <SectionTitle>Financial statistics</SectionTitle>
            <StatTable
              rows={[
                ["Revenue", usdBillions(fin.revenue)],
                ["Net income", usdBillions(fin.netIncome)],
                ["Profit margin", `${fin.profitMargin}%`],
                ["Return on equity", `${fin.roe}%`],
                ["P/E ratio", `${fin.peRatio}`],
                ["Dividend yield", `${fin.dividendYield}%`],
                ["Debt / equity", `${fin.debtToEquity}`],
                ["1Y total return", signedPercent(fin.oneYearReturn, 1)],
              ]}
            />
          </Panel>
        </Reveal>
        <Reveal delay={160}>
          <Panel>
            <SectionTitle>ESG metrics</SectionTitle>
            <StatTable
              rows={[
                ["Carbon intensity", `${esg.carbonIntensity} tCO₂e/$M`],
                ["Renewable energy", `${esg.renewableEnergyPct}%`],
                ["Board independence", `${esg.boardIndependencePct}%`],
                ["Gender diversity", `${esg.genderDiversityPct}%`],
                ["Employee turnover", `${esg.employeeTurnover}%`],
                ["Controversy level", `${esg.controversyLevel} / 5`],
              ]}
            />
          </Panel>
        </Reveal>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Reveal delay={120}>
          <Panel>
            <SectionTitle>Controversy timeline</SectionTitle>
            {company.controversies.length === 0 ? (
              <p className="mt-4 text-sm text-muted">
                No material controversies on record.
              </p>
            ) : (
              <ul className="mt-4 space-y-4">
                {company.controversies.map((c, i) => (
                  <ControversyRow key={i} controversy={c} />
                ))}
              </ul>
            )}
          </Panel>
        </Reveal>

        <Reveal delay={160}>
          <Panel>
            <SectionTitle>Sector peers</SectionTitle>
            <ul className="mt-3 divide-y divide-hairline">
              {peers.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => openCompany(p.id)}
                    className="flex w-full items-center gap-3 py-2.5 text-left transition hover:opacity-80"
                  >
                    <CompanyLogo company={p} size={32} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {p.name}
                      </span>
                      <span className="block text-[11px] text-faint">
                        {p.ticker} · {p.region}
                      </span>
                    </span>
                    <span className="font-mono text-sm tabular-nums text-txt">
                      {p.esgScore}
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 text-[10px] font-bold text-canvas"
                      style={{ background: gradeColor[p.grade] }}
                    >
                      {p.grade}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </Reveal>
      </div>

      <footer className="py-8 text-center text-xs text-faint">
        Headline identity is real; ESG scores and operating metrics are
        illustrative models, not investment advice.
      </footer>
    </div>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full rounded-xl border border-hairline bg-surface p-5">
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-faint">
      {children}
    </h2>
  );
}

function Kpi({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg";
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
        {label}
      </p>
      <p
        className={`mt-1 font-mono text-xl font-semibold tabular-nums ${
          tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-txt"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function PercentileBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-mono tabular-nums text-txt">{value}th pct</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-raised">
        <div
          className="h-full rounded-full"
          style={{
            width: `${value}%`,
            background: color,
            transition: "width 0.7s cubic-bezier(0.22,1,0.36,1)",
          }}
        />
      </div>
    </div>
  );
}

const SEVERITY_STYLE: Record<
  Controversy["severity"],
  { color: string; label: string }
> = {
  high: { color: "#ec6a5e", label: "High" },
  medium: { color: "#e0b24a", label: "Medium" },
  low: { color: "#9a968e", label: "Low" },
};

function ControversyRow({ controversy }: { controversy: Controversy }) {
  const style = SEVERITY_STYLE[controversy.severity];
  return (
    <li className="flex items-start gap-3">
      <span
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
        style={{ background: `${style.color}22`, color: style.color }}
      >
        <AlertTriangle size={14} />
      </span>
      <div className="flex-1">
        <p className="text-sm text-txt">{controversy.title}</p>
        <p className="text-[11px] text-faint">
          {controversy.year} ·{" "}
          <span style={{ color: style.color }}>{style.label} severity</span>
        </p>
      </div>
    </li>
  );
}

function StatTable({ rows }: { rows: [string, string][] }) {
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-hairline">
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([k, v], i) => (
            <tr key={k} className={i % 2 === 0 ? "" : "bg-white/[0.015]"}>
              <td className="px-4 py-2.5 text-muted">{k}</td>
              <td className="px-4 py-2.5 text-right font-mono font-medium tabular-nums text-txt">
                {v}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
