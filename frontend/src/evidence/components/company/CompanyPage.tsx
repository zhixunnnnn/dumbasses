import { useMemo } from "react";
import { Activity, ArrowLeft, Check, Leaf, Minus, X } from "lucide-react";
import { api, useApi } from "../../lib/api";
import type { TraceNode } from "../../types";
import { na, PILLAR_COLOR } from "../../lib/ui";
import ProvenanceBadge from "../common/ProvenanceBadge";
import { useNavigation } from "../../navigation/NavigationContext";
import { Gauge, LineChart } from "../charts";
import Why from "../common/Why";
import { ImproverPill, QuadrantBadge } from "../common/badges";
import PriceWitness from "./PriceWitness";
import ClaimTable from "./ClaimTable";
import ComplianceGap from "./ComplianceGap";
import SatelliteVerification from "./SatelliteVerification";
import ForecastCard from "./ForecastCard";
import TrustMeter from "./TrustMeter";
import PeerDistribution from "./PeerDistribution";
import LiveNews from "./LiveNews";
import PeerTable from "./PeerTable";
import LiveResearchClaims from "./LiveResearchClaims";
import ImpactMateriality from "./ImpactMateriality";
import FinancialsPanel from "./FinancialsPanel";
import MaterialityWeights from "./MaterialityWeights";
import DoubleMaterialityPanel from "./DoubleMaterialityPanel";
import { usePublishAssistantPageContext } from "../../../components/chat/PageContext";

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
  const { goBack } = useNavigation();
  const { data, loading, error } = useApi(() => api.company(id), [id]);
  const pageContext = useMemo(() => data ? ({
    route: "evidenceCompany",
    title: `${data.company.name} ESG evidence profile`,
    company: data.company,
    rating: data.rating,
    ratingSeries: data.rating_series,
    impact: data.impact ?? null,
    doubleMateriality: data.double_materiality ?? null,
    fundamentals: data.fundamentals ?? null,
    evidence: data.evidence,
    evidenceSeries: data.series,
    raters: data.raters,
    signal: data.signal,
    compliance: data.compliance,
    forecast: data.forecast,
    claims: data.claims,
    liveIntelligence: data.liveIntelligence ?? null,
    peers: data.peers,
  }) : ({ route: "evidenceCompany", title: `Company ${id}`, companyId: id }), [data, id]);
  usePublishAssistantPageContext(pageContext);

  if (loading) return <div className="p-10 text-sm text-muted">Loading {id}…</div>;
  if (error || !data) return <div className="p-10 text-sm text-neg">Couldn’t load {id}. {error}</div>;

  const { company, rating, impact, series, raters, signal, witness, compliance, forecast, claims, peers, liveIntelligence } = data;
  const latestReal = data.latest_real_raters ?? null;
  const cdpDisclosure = data.cdp_disclosure ?? null;
  // the analysis year comes from the data, not a hardcoded constant that could drift
  const analysisYear = series.length ? series[series.length - 1].year : undefined;
  const seriesPts = series.filter((s) => s.total !== null);
  // peers carry both scores; the peer widgets read `evidence_total`, so pass the RATING
  // through that field to reuse them unchanged now that the rating is the headline score.
  const ratingPeers = peers.map((p) => ({ id: p.id, name: p.name, evidence_total: p.rating_total }));
  // SASB materiality share per pillar (sum of its topics' weights) — the pillar weighting
  // used in the total, driven by materiality %, never by a topic count.
  const pillarWeight = (p: "E" | "S" | "G") =>
    (rating.topic_breakdown ?? []).filter((t) => t.pillar === p).reduce((a, t) => a + t.weight, 0);

  const realRaters = raters.real_raters ?? [];
  // S&P is dropped (not publicly obtainable), so it is not shown as a rater channel.
  const consensusTrace = node("Rater consensus (mean of the REAL percentiles, higher=better)", raters.consensus, [
    node(`MSCI percentile`, raters.msci_pct),
    node(`Sustainalytics percentile (inverted)`, raters.sustainalytics_pct),
    node(`CDP percentile`, raters.cdp_pct),
    node(`real ratings: ${realRaters.length ? realRaters.join(", ") : "none"}`, null),
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
            {signal.quadrant && (
              <ProvenanceBadge provenance={signal.quadrant_provenance}
                contributing={raters.contributing} real={realRaters} />
            )}
            {signal.is_underpriced_improver && <ImproverPill />}
          </div>
          <p className="mt-1 font-mono text-[12px] text-faint">
            {company.ticker} · {company.exchange} · {company.sector} · {company.sasb_industry} · {company.country}
          </p>
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end gap-2">
            <span className="font-mono text-3xl font-semibold text-txt">{na(rating.total)}</span>
            <Why trace={rating.trace} title="ESG rating" />
            {rating.provenance && (
              <ProvenanceBadge provenance={rating.provenance}
                contributing={raters.contributing} real={realRaters} />
            )}
          </div>
          <p className="text-[11px] text-faint">
            ESG Rating · SASB-weighted · E objective, S/G agency-referenced
          </p>
          <p className="text-[11px] text-faint">
            E: CDP + Climate TRACE · S/G ref: {rating.agencies.length ? rating.agencies.map((a) => a.toUpperCase()).join(", ") : "none"}
          </p>
        </div>
      </div>

      {/* CGS finance view — valuation, analyst target, dividend — leads the page */}
      <FinancialsPanel f={data.fundamentals} />

      {/* the two panels */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium text-muted">Peer distribution</p>
            <Why trace={node(`ESG ratings of ${company.sector} companies in the panel; the green bar is ${company.name}`, rating.total)}
              title="Peer distribution" />
          </div>
          <PeerDistribution self={rating.total} selfId={id} selfName={company.name}
            peers={ratingPeers} sector={company.sector} />
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium text-muted">Trust Meter · divergence</p>
            <Why trace={node("Divergence = max − min of rater percentiles", raters.divergence, consensusTrace.children)}
              title="Divergence" />
          </div>
          <p className="mt-1 flex items-center gap-2 font-mono text-2xl font-semibold text-txt">
            {na(raters.divergence)}
            {/* divergence is real-only; the badge only appears when a real number exists */}
            {raters.divergence !== null && (
              <ProvenanceBadge provenance={raters.divergence_provenance}
                contributing={raters.contributing} real={realRaters} />
            )}
          </p>
          <TrustMeter raters={raters} latestReal={latestReal}
            cdpDisclosure={cdpDisclosure} year={analysisYear} />
        </div>
      </div>

      {/* signal legs — redefined around the real emission trajectory */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-hairline bg-surface px-4 py-3 shadow-panel">
        <span className="text-[12px] font-medium text-muted">Decarbonising Improver =</span>
        <Leg ok={signal.momentum == null ? null : signal.momentum >= 3}
          label="emissions falling ≥3%/yr (Climate TRACE)" />
        <Leg ok={signal.price_flat} label="price flat (market hasn't priced it)" />
        <span className="ml-1 text-[12px] text-muted">→</span>
        {signal.is_underpriced_improver
          ? <span className="text-[12px] font-semibold text-pos">(decarbonising, unpriced)</span>
          : <span className="text-[12px] text-faint">not both met</span>}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center gap-2 text-muted">
            <Leaf size={14} className="text-pos" />
            <p className="text-[12px] font-medium">Sustainable energy use</p>
          </div>
          <p className={`mt-2 text-lg font-semibold ${
            liveIntelligence?.renewable.renewable_status === "Verified"
              ? "text-pos"
              : liveIntelligence?.renewable.renewable_status === "Non-verified"
                ? "text-profit"
                : "text-muted"
          }`}>
            {liveIntelligence?.renewable.renewable_status ?? "No evidence found"}
          </p>
          <p className="mt-1 text-[11px] text-faint">
            {liveIntelligence?.renewable.evidence_count ?? 0} grouped claims · {liveIntelligence?.renewable.verified_count ?? 0} verified
          </p>
          {/* A renewables developer can have plenty of renewable coverage and still
              evidence none of its OWN use — say that, rather than implying no data. */}
          {(liveIntelligence?.renewable.evidence_count ?? 0) === 0
            && (liveIntelligence?.renewable.renewable_mentions ?? 0) > 0 && (
            <p className="mt-1 text-[11px] text-faint">
              {liveIntelligence?.renewable.renewable_mentions} renewable claims found, none
              evidencing the company&apos;s own use.
            </p>
          )}
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <div className="flex items-center gap-2 text-muted">
            <Activity size={14} className="text-purpose" />
            <p className="text-[12px] font-medium">Emissions direction</p>
          </div>
          <p className={`mt-2 text-lg font-semibold ${
            liveIntelligence?.renewable.emissions_trend === "Falling"
              ? "text-pos"
              : liveIntelligence?.renewable.emissions_trend === "Rising"
                ? "text-neg"
                : "text-muted"
          }`}>
            {liveIntelligence?.renewable.emissions_trend ?? "No evidence found"}
          </p>
          <p className="mt-1 text-[11px] text-faint">Separate evidence signal; it does not prove renewable use.</p>
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <p className="text-[12px] font-medium text-muted">Validated web research</p>
          <p className="mt-2 text-lg font-semibold text-txt">{liveIntelligence?.claims.length ?? 0} claims</p>
          <p className="mt-1 text-[11px] text-faint">
            Community adjustment {liveIntelligence?.community_sentiment_adjustment ?? 0} pts, live signal only
          </p>
        </div>
      </div>

      {/* pillars + evidence trajectory */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1.3fr]">
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <h3 className="mb-2 text-sm font-semibold text-txt">ESG rating by pillar</h3>
          <div className="flex justify-around">
            {(["E", "S", "G"] as const).map((p) => {
              const w = (rating.topic_breakdown ?? [])
                .filter((t) => t.pillar === p)
                .reduce((a, t) => a + t.weight, 0);
              return (
                <div key={p} className="flex flex-col items-center">
                  <Gauge value={rating.pillars[p] ?? 0}
                    label={p === "E" ? "Environmental" : p === "S" ? "Social" : "Governance"}
                    color={PILLAR_COLOR[p]} size={92} />
                  <span className="mt-0.5 font-mono text-[10px] text-faint">
                    SASB weight {Math.round(w)}%
                  </span>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] text-faint">
            Pillars are weighted into the rating by <span className="text-muted">SASB materiality</span>{" "}
            (E {Math.round(pillarWeight("E"))}% · S {Math.round(pillarWeight("S"))}% · G {Math.round(pillarWeight("G"))}%
            for {company.sasb_industry}) — the materiality %, never a topic count. Each pillar uses
            REAL evidence where we have it: <span className="text-muted">E</span> from CDP + Climate
            TRACE, <span className="text-muted">S</span> from the company&apos;s workforce-safety
            disclosures, <span className="text-muted">G</span> from its grid-resiliency disclosures.
            A pillar with no real signal falls back to the rating agencies as a reference.
          </p>
        </div>
        <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
          <h3 className="mb-2 text-sm font-semibold text-txt">Emission trajectory</h3>
          {impact && impact.annual && impact.annual.length > 1 ? (
            <>
              <LineChart data={impact.annual.map((a) => Math.round((a.emissions / 1e6) * 100) / 100)}
                labels={impact.annual.map((a) => String(a.year))} color="#ec6f63" valueSuffix=" Mt" />
              <p className="mt-1 text-[11px] text-faint">
                {impact.annual.map((a) => a.year).join(" → ")} · real owned-asset CO₂e (Climate TRACE)
                {(() => {
                  const a = impact.annual;
                  const d = (a[a.length - 1].emissions - a[0].emissions) / 1e6;
                  return ` · ${d >= 0 ? "↑" : "↓"} ${Math.abs(d).toFixed(1)} Mt since ${a[0].year}`;
                })()}
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">
              No multi-year Climate TRACE coverage for this owner — trajectory N.A.
            </p>
          )}
        </div>
      </div>

      <MaterialityWeights rating={rating} industry={company.sasb_industry} />

      <ImpactMateriality impact={impact} />

      <DoubleMaterialityPanel dm={data.double_materiality} />

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

      {liveIntelligence && liveIntelligence.claims.length > 0 && (
        <LiveResearchClaims claims={liveIntelligence.claims} />
      )}

      <SatelliteVerification companyId={id} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ComplianceGap compliance={compliance} />
        <ForecastCard forecast={forecast} />
      </div>

      <LiveNews companyId={id} />

      {peers.length > 0 && (
        <PeerTable
          peers={ratingPeers}
          selfId={id}
          selfName={company.name}
          selfTotal={rating.total}
          sector={company.sector ?? null}
        />
      )}

    </div>
  );
}
