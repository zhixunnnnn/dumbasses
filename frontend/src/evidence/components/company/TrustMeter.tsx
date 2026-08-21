import type { CdpDisclosure, LatestRealRater, RaterKey, Raters } from "../../types";
import { na, provenanceDetail } from "../../lib/ui";

const RATERS: { key: RaterKey; pct: keyof Raters; label: string; color: string }[] = [
  { key: "msci", pct: "msci_pct", label: "MSCI", color: "#4cc4d4" },
  { key: "sp", pct: "sp_pct", label: "S&P", color: "#e0b24a" },
  { key: "sustainalytics", pct: "sustainalytics_pct", label: "Sustainalytics", color: "#a78bfa" },
  { key: "cdp", pct: "cdp_pct", label: "CDP", color: "#3ecf8e" },
];

const RATER_NAME: Record<string, string> = {
  msci: "MSCI", sp: "S&P", sustainalytics: "Sustainalytics", cdp: "CDP",
};

export default function TrustMeter({
  raters,
  latestReal,
  cdpDisclosure,
  year,
}: {
  raters: Raters;
  latestReal?: LatestRealRater[] | null;
  cdpDisclosure?: CdpDisclosure | null;
  year?: number;
}) {
  const realKeys = new Set<RaterKey>(raters.real_raters ?? []);
  const provenance = raters.rater_provenance;
  const vals = RATERS
    .map((r) => ({ ...r, v: raters[r.pct] as number | null, real: realKeys.has(r.key) }))
    .filter((r) => r.v !== null);

  const div = raters.divergence;
  // Shade the span the spread was ACTUALLY computed over, whatever its provenance —
  // drawing a different set than the number describes would be its own small lie.
  const contributing = new Set<RaterKey>(raters.contributing ?? []);
  const spanVals = vals.filter((r) => contributing.has(r.key)).map((r) => r.v as number);
  const trust =
    div === null ? { label: "N.A.", color: "#6a665f" }
      : div > 33 ? { label: "High disagreement", color: "#ec6a5e" }
        : div > 15 ? { label: "Moderate disagreement", color: "#e0b24a" }
          : { label: "Raters aligned", color: "#3ecf8e" };

  const lo = spanVals.length ? Math.min(...spanVals) : 0;
  const hi = spanVals.length ? Math.max(...spanVals) : 0;
  const sources = RATERS
    .map((r) => ({ label: r.label, p: provenance?.[r.key] }))
    .filter((r) => r.p?.real && r.p?.source);
  // A company that declined to answer CDP is not a company with a bad CDP score.
  const declined = RATERS
    .map((r) => ({ label: r.label, p: provenance?.[r.key] }))
    .filter((r) => !r.p?.real && r.p?.status);

  return (
    <div>
      <div className="relative mt-1 h-9">
        <div className="absolute left-0 right-0 top-4 h-1 rounded bg-raised" />
        {div !== null && spanVals.length >= 2 && (
          <div className="absolute top-4 h-1 rounded" style={{
            left: `${lo}%`, width: `${hi - lo}%`, backgroundColor: trust.color, opacity: 0.4,
          }} />
        )}
        {vals.map((r) => (
          <div key={r.label} className="group absolute -translate-x-1/2" style={{ left: `${r.v}%`, top: 0 }}>
            <div className="mx-auto h-4 w-0.5" style={{ backgroundColor: r.color }} />
            {/* solid marker = real (sourced); hollow marker = illustrative */}
            <div
              className="h-2.5 w-2.5 rounded-full ring-2 ring-surface"
              style={r.real
                ? { backgroundColor: r.color }
                : { backgroundColor: "transparent", border: `1.5px solid ${r.color}` }}
              title={`${r.label}: ${r.v} (${r.real ? "real" : "illustrative"})`}
            />
          </div>
        ))}
      </div>

      <div className="mt-1 flex items-center justify-between">
        <div className="flex flex-wrap gap-3">
          {vals.map((r) => (
            <span key={r.label} className="inline-flex items-center gap-1 text-[10.5px] text-muted">
              <span className="h-2 w-2 rounded-full"
                style={r.real ? { backgroundColor: r.color } : { backgroundColor: "transparent", border: `1.5px solid ${r.color}` }} />
              {r.label} {na(r.v, 0)}
              <span className={r.real ? "text-pos" : "text-faint"}>{r.real ? "· real" : "· illus."}</span>
            </span>
          ))}
        </div>
        <span className="text-[11px] font-medium" style={{ color: trust.color }}>
          {trust.label}
        </span>
      </div>

      <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[10px] leading-snug text-faint">
        <span><span className="text-muted">●</span> real (sourced) · <span className="text-muted">○</span> illustrative.</span>
        {div !== null && (
          <span>
            Spread over {provenanceDetail(raters.contributing, raters.real_raters) || "no channels"}.
          </span>
        )}
        {declined.map(({ label, p }) => (
          <span key={`${label}-status`}>
            {label}: did not disclose{p!.observed_on ? ` (${p!.observed_on})` : ""} — not a
            score, so not ranked.
          </span>
        ))}
        {sources.map(({ label, p }) => (
          <span key={label}>
            {label}:{" "}
            {p!.url ? (
              <a href={p!.url} target="_blank" rel="noreferrer" className="text-pos hover:underline">
                {p!.source}
              </a>
            ) : (
              <span className="text-pos">{p!.source}</span>
            )}
            {p!.observed_on ? ` (${p!.observed_on})` : ""}
          </span>
        ))}
      </p>

      {/* Real observations that fall OUTSIDE the analysis year. They are shown with their
          own year and never folded into the figures above -- re-dating a measurement to
          make it fit the window would be a fabrication. */}
      {(latestReal?.length || cdpDisclosure) && (
        <div className="mt-2 border-t border-hairline pt-1.5">
          <p className="text-[10px] font-medium text-muted">
            Latest real rating on record{year ? ` (outside the ${year} window)` : ""}
          </p>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {(latestReal ?? []).map((r) => (
              <span key={r.rater} className="inline-flex items-center gap-1 text-[10.5px]">
                <span className="h-2 w-2 rounded-full bg-pos" />
                <span className="text-muted">
                  {RATER_NAME[r.rater] ?? r.rater} <span className="font-mono">{r.value}</span>
                  {" · "}{r.year}
                </span>
                {r.url ? (
                  <a href={r.url} target="_blank" rel="noreferrer" className="text-pos hover:underline">
                    real ({r.source})
                  </a>
                ) : (
                  <span className="text-pos">real ({r.source})</span>
                )}
              </span>
            ))}
            {cdpDisclosure && (
              <span className="inline-flex items-center gap-1 text-[10.5px] text-faint">
                <span className="h-2 w-2 rounded-full border border-faint" />
                CDP {cdpDisclosure.year}: did not disclose — a fact, not a score, so never ranked.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
