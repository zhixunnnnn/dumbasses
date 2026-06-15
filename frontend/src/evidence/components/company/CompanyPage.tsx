import { ArrowLeft, Check, X, Minus } from "lucide-react";
import { api, useApi } from "../../lib/api";
import type { TraceNode } from "../../types";
import { na, signed, PILLAR_COLOR } from "../../lib/ui";
import { useNavigation } from "../../navigation/NavigationContext";
import { Gauge, LineChart } from "../charts";
import Why from "../common/Why";
import { ImproverPill, QuadrantBadge } from "../common/badges";
import PriceWitness from "./PriceWitness";
import ClaimTable from "./ClaimTable";
import ComplianceGap from "./ComplianceGap";
import ForecastCard from "./ForecastCard";
import TrustMeter from "./TrustMeter";
import LiveNews from "./LiveNews";

function node(label: string, value: number | null, children: TraceNode[] = []): TraceNode {
  return { label, value, contribution: null, source_sentence: null, source_doc: null, source_page: null, children };
}

function Leg({ ok, label }: { ok: boolean | null; label: string }) {
  const Icon = ok === true ? Check : ok === false ? X : Minus;
  const color = ok === true ? "#3ecf8e" : ok === false ? "#ef6f63" : "#6a665f";
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-hairline px-2 py-1 text-[11px]"
      style={{ color }}>
      <Icon size={12} /> {label}
    </span>
  );
}

export default function CompanyPage({ id }: { id: string }) {
  const { goBack, navigate } = useNavigation();
  const { data, loading, error } = useApi(() => api.company(id), [id]);

  if (loading) return <div className="p-10 text-sm text-muted">Loading {id}…</div>;
  if (error || !data) return <div className="p-10 text-sm text-neg">Couldn’t load {id}. {error}</div>;

  const { company, evidence, series, raters, signal, witness, compliance, forecast, claims, peers } = data;
  const seriesPts = series.filter((s) => s.total !== null);

  const consensusTrace = node("Rater consensus (mean of available, higher=better)", raters.consensus, [
    node(`MSCI percentile`, raters.msci_pct),
    node(`S&P percentile`, raters.sp_pct),
    node(`Sustainalytics percentile (inverted)`, raters.sustainalytics_pct),
  ]);

  return (
    <div className="mx-auto max-w-[1180px] space-y-5 p-5 md:p-7">
      <button onClick={goBack} className="inline-flex items-center gap-1.5 text-[12px] text-muted hover:text-txt">
        <ArrowLeft size={14} /> Back to screener
      </button>

      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-semibold text-txt">{company.name}</h1>
            <QuadrantBadge q={signal.quadrant} />
            {signal.is_underpriced_improver && <ImproverPill />}
          </div>
          <p className="mt-1 font-mono text-[12px] text-faint">
            {company.ticker} · {company.exchange} · {company.sector} · {company.sasb_industry} · {company.country}
          </p>
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end gap-2">
            <span className="font-mono text-3xl font-semibold text-txt">{na(evidence.total)}</span>
            <Why trace={evidence.trace} title="Evidence score" />
          </div>
          <p className="text-[11px] text-faint">Evidence score · confidence {Math.round(evidence.confidence * 100)}%</p>
        </div>
      </div>

      {/* the three numbers */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium text-muted">Rater consensus</p>
            <Why trace={consensusTrace} title="Consensus" />
          </div>
          <p className="mt-1 font-mono text-2xl font-semibold text-txt">{na(raters.consensus)}</p>
          <p className="text-[11px] text-faint">percentile vs sector</p>
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium text-muted">Trust Meter · divergence</p>
            <Why trace={node("Divergence = max − min of rater percentiles", raters.divergence, consensusTrace.children)}
              title="Divergence" />
          </div>
          <p className="mt-1 font-mono text-2xl font-semibold text-txt">{na(raters.divergence)}</p>
          <TrustMeter raters={raters} />
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium text-muted">Evidence gap</p>
            <Why trace={signal.trace} title="Underpriced Improver signal" />
          </div>
          <p className="mt-1 font-mono text-2xl font-semibold"
            style={{ color: (signal.evidence_gap ?? 0) > 0 ? "#3ecf8e" : "#9a968e" }}>
            {signed(signal.evidence_gap)}
          </p>
          <p className="text-[11px] text-faint">evidence percentile − consensus</p>
        </div>
      </div>

      {/* signal legs */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-hairline bg-surface px-4 py-3 shadow-panel">
        <span className="text-[12px] font-medium text-muted">Underpriced Improver =</span>
        <Leg ok={signal.proof_up} label="proof_up (verified evidence ↑)" />
        <Leg ok={signal.opinion_flat} label="opinion_flat (raters stale/split)" />
        <Leg ok={signal.price_flat} label="price_flat (market hasn't reacted)" />
        <span className="ml-1 text-[12px] text-muted">→</span>
        {signal.is_underpriced_improver
          ? <span className="text-[12px] font-semibold text-pos">YES — the gap the market missed</span>
          : <span className="text-[12px] text-faint">not all three legs met</span>}
      </div>

      {/* pillars + evidence trajectory */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1.3fr]">
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <h3 className="mb-2 text-sm font-semibold text-txt">Evidence by pillar</h3>
          <div className="flex justify-around">
            {(["E", "S", "G"] as const).map((p) => (
              <Gauge key={p} value={evidence.pillars[p] ?? 0}
                label={p === "E" ? "Environmental" : p === "S" ? "Social" : "Governance"}
                color={PILLAR_COLOR[p]} size={92} />
            ))}
          </div>
          {evidence.absent_topics.length > 0 && (
            <p className="mt-2 text-[11px] text-faint">
              Undisclosed material topics: {evidence.absent_topics.join(", ")} — lowers confidence, not the score.
            </p>
          )}
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <h3 className="mb-2 text-sm font-semibold text-txt">Verified-evidence trajectory</h3>
          {seriesPts.length > 1 && (
            <LineChart data={seriesPts.map((s) => s.total as number)}
              labels={seriesPts.map((s) => String(s.year))} color="#4cc4d4" valueSuffix="" />
          )}
          <p className="mt-1 text-[11px] text-faint">
            {seriesPts.map((s) => s.year).join(" → ")} · momentum {signed(signal.momentum)} / yr
          </p>
        </div>
      </div>

      {/* PRICE WITNESS */}
      <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
        <div className="mb-1 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-txt">Price Witness</h3>
            <p className="text-[11px] text-faint">
              Flat price under a rising verified-evidence band = the gap you can see.
            </p>
          </div>
        </div>
        <PriceWitness witness={witness} series={series} />
      </div>

      <ClaimTable
        claims={claims.claims}
        absent={claims.absent}
        live={claims.live}
        sourceUrl={claims.source_url}
        sourceTitle={claims.source_title}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ComplianceGap compliance={compliance} />
        <ForecastCard forecast={forecast} />
      </div>

      <LiveNews companyId={id} />

      {/* peers */}
      {peers.length > 0 && (
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <h3 className="mb-2 text-sm font-semibold text-txt">Sector peers</h3>
          <div className="flex flex-wrap gap-2">
            {peers.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate({ name: "evidenceCompany", id: p.id })}
                className="rounded-md border border-hairline bg-canvas/40 px-3 py-1.5 text-[12px] text-muted transition hover:border-pos/40 hover:text-txt">
                {p.name} <span className="font-mono text-faint">· {na(p.evidence_total)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
