import { ExternalLink, Factory } from "lucide-react";
import type { ImpactMateriality as Impact } from "../../types";

// tonnes -> a compact "19.8 Mt" / "404.9 kt" label.
function fmtTonnes(t: number | null): string {
  if (t == null) return "N.A.";
  if (t >= 1e6) return `${(t / 1e6).toFixed(1)} Mt`;
  if (t >= 1e3) return `${(t / 1e3).toFixed(0)} kt`;
  return `${Math.round(t)} t`;
}

const prettySub = (s: string | null) =>
  (s ?? "").replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Other";

export default function ImpactMateriality({ impact }: { impact?: Impact | null }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center gap-2">
        <Factory size={15} className="text-purpose" />
        <h3 className="text-sm font-semibold text-txt">Impact materiality · Climate TRACE</h3>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-faint">
        The ESG rating is <span className="text-muted">financial materiality</span> — how the
        world&apos;s ESG risks price back into the company. This is the other half:{" "}
        <span className="text-muted">impact materiality</span> — the real CO<sub>2</sub>e the
        company&apos;s own power assets emit into the world.
      </p>

      {!impact || impact.total_emissions_tonnes == null ? (
        <p className="mt-3 text-[12px] text-faint">
          No Climate TRACE owner match — impact is <span className="font-mono">N.A.</span> Nothing
          is estimated in its place.
        </p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-3xl font-semibold text-txt">
                {fmtTonnes(impact.total_emissions_tonnes)}
                <span className="ml-1 text-[13px] font-normal text-faint">CO₂e · {impact.year}</span>
              </p>
              <p className="mt-0.5 text-[11px] text-faint">
                {impact.owner_name} · {impact.asset_count} owned asset{impact.asset_count === 1 ? "" : "s"}
              </p>
            </div>
            <div className="text-right">
              {impact.rank != null && impact.peers != null && (
                <p className="font-mono text-sm text-txt">
                  #{impact.rank} of {impact.peers} emitters
                </p>
              )}
              {impact.panel_share != null && (
                <p className="text-[11px] text-faint">
                  {Math.round(impact.panel_share * 100)}% of covered-panel emissions
                </p>
              )}
            </div>
          </div>

          {impact.top_assets.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[11px] font-medium text-muted">Top emitting assets</p>
              <ul className="space-y-1">
                {impact.top_assets.slice(0, 5).map((a, i) => {
                  const share = impact.total_emissions_tonnes
                    ? (a.emissions ?? 0) / impact.total_emissions_tonnes
                    : 0;
                  return (
                    <li key={i} className="flex items-center gap-2 text-[12px]">
                      <span className="w-40 shrink-0 truncate text-txt" title={a.name ?? ""}>
                        {a.name ?? "—"}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised">
                        <div className="h-full rounded-full bg-purpose/70"
                          style={{ width: `${Math.max(2, share * 100)}%` }} />
                      </div>
                      <span className="w-14 shrink-0 text-right font-mono text-faint">
                        {fmtTonnes(a.emissions)}
                      </span>
                      <span className="w-24 shrink-0 truncate text-right text-[10px] text-faint"
                        title={prettySub(a.subsector)}>
                        {prettySub(a.subsector)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {impact.note && (
            <p className="mt-2 text-[10px] leading-snug text-faint">{impact.note}</p>
          )}
          <p className="mt-2 flex items-center gap-2 text-[10px] text-faint">
            <span>Real owned-asset emissions · {impact.source}</span>
            {impact.source_url && (
              <a href={impact.source_url} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 underline-offset-2 hover:text-pos hover:underline">
                Climate TRACE <ExternalLink size={10} />
              </a>
            )}
          </p>
        </>
      )}
    </div>
  );
}
