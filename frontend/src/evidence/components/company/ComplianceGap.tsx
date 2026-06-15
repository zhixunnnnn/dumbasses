import { ExternalLink } from "lucide-react";
import type { Compliance } from "../../types";
import { RegBadge } from "../common/badges";
import Why from "../common/Why";

export default function ComplianceGap({ compliance }: { compliance: Compliance }) {
  const all = [
    ...compliance.met,
    ...compliance.partial,
    ...compliance.missing,
    ...compliance.not_in_force,
  ];
  const anyLive = all.some((r) => r.scraped);
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-txt">Regulatory compliance gap</h3>
          <p className="text-[11px] text-faint">SGX · ISSB · MAS · ASEAN Taxonomy</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-lg font-semibold"
            style={{ color: (compliance.score ?? 0) > 0 ? "#e0b24a" : "#3ecf8e" }}>
            {compliance.score === null ? "N.A." : `${Math.round(compliance.score * 100)}%`}
          </span>
          <Why trace={compliance.trace} title="Compliance gap" />
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {all.map((r) => (
          <div key={r.reg_id} className="text-[12px]">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="truncate text-muted">{r.name}</span>
                {r.scraped && (
                  <span title="Checked against the company's published report (live)"
                    className="shrink-0 rounded bg-pos/15 px-1 py-px text-[8.5px] font-semibold uppercase tracking-wide text-pos">
                    Live
                  </span>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {r.source_url && (
                  <a href={r.source_url} target="_blank" rel="noreferrer" title={r.source_url}
                    className="text-faint transition hover:text-pos">
                    <ExternalLink size={12} />
                  </a>
                )}
                <RegBadge status={r.status} />
              </div>
            </div>
            {r.scraped && r.source_excerpt && (
              <p className="mt-1 border-l-2 border-hairline pl-2 text-[10.5px] italic leading-snug text-faint">
                “{r.source_excerpt}”
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[10.5px] leading-snug text-faint">
        {anyLive && (
          <><span className="text-pos">Live</span> = verified against the company’s published report (scraped via Bright Data); MISSING means the required disclosure was absent in the retrieved report. </>
        )}
        A regulation not yet in force (e.g. ISSB S2, effective 2025) is a readiness gap — never a violation.
        Unknown status is excluded, never counted as missing.
      </p>
    </div>
  );
}
