import { useState } from "react";
import { ExternalLink, Globe } from "lucide-react";
import type { LiveResearchClaim, LiveResearchSource } from "../../types";

const CLASS_STYLE: Record<string, { color: string; label: string }> = {
  verified: { color: "pos", label: "verified source" },
  non_verified: { color: "profit", label: "unlisted source" },
  community: { color: "purpose", label: "community" },
};

const prettyTopic = (t: string) => t.replace(/_/g, " ");

/** Keep the first source per domain, preferring the most trusted class for that domain. */
function dedupeByDomain(sources: LiveResearchSource[]): LiveResearchSource[] {
  const rank = (v: string) => (v === "verified" ? 0 : v === "non_verified" ? 1 : 2);
  const best = new Map<string, LiveResearchSource>();
  for (const s of sources) {
    const held = best.get(s.domain);
    if (!held || rank(s.source_class) < rank(held.source_class)) best.set(s.domain, s);
  }
  return [...best.values()];
}

/** Live web-research claims, with the source class of every backing domain shown inline.
 *  A claim counts as verified only when one of its sources is on the verified-domain
 *  registry — without showing the domains, a "Non-verified" verdict looks arbitrary. */
export default function LiveResearchClaims({ claims }: { claims: LiveResearchClaim[] }) {
  const [showAll, setShowAll] = useState(false);
  if (!claims.length) return null;

  const LIMIT = 6;
  const sorted = [...claims].sort((a, b) => {
    const rank = (v: string) => (v === "verified" ? 0 : v === "non_verified" ? 1 : 2);
    return rank(a.verification) - rank(b.verification);
  });
  const shown = showAll ? sorted : sorted.slice(0, LIMIT);
  const verified = claims.filter((c) => c.verification === "verified").length;

  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-txt">Live web research</h3>
          <p className="text-[11px] text-faint">
            {claims.length} grouped claim{claims.length === 1 ? "" : "s"} · {verified} verified.
            A claim is verified only when a source sits on the verified-domain registry.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {Object.entries(CLASS_STYLE).map(([key, s]) => (
            <span key={key}
              className="rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide"
              style={{
                color: `rgb(var(--color-${s.color}))`,
                borderColor: `rgb(var(--color-${s.color}) / 0.35)`,
              }}>
              {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className={`divide-y divide-hairline/60${showAll ? " max-h-[440px] overflow-y-auto" : ""}`}>
        {shown.map((c) => {
          const style = CLASS_STYLE[c.verification] ?? CLASS_STYLE.non_verified;
          return (
            <div key={c.claim_id} className="px-4 py-2.5">
              <div className="flex items-start gap-2.5">
                <span
                  className="mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase"
                  style={{
                    color: `rgb(var(--color-${style.color}))`,
                    borderColor: `rgb(var(--color-${style.color}) / 0.35)`,
                    backgroundColor: `rgb(var(--color-${style.color}) / 0.10)`,
                  }}>
                  {c.verification === "non_verified" ? "unlisted" : c.verification}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[12.5px] leading-snug text-txt">{c.claim_text}</p>
                  <p className="mt-0.5 text-[10px] text-faint">{prettyTopic(c.topic)}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {/* one chip per domain — several URLs from the same site say nothing extra */}
                    {dedupeByDomain(c.sources).map((s) => {
                      const ss = CLASS_STYLE[s.source_class] ?? CLASS_STYLE.non_verified;
                      return (
                        <a key={s.url} href={s.url} target="_blank" rel="noreferrer"
                          title={`${s.domain} — ${ss.label}`}
                          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] transition hover:bg-raised/50"
                          style={{
                            color: `rgb(var(--color-${ss.color}))`,
                            borderColor: `rgb(var(--color-${ss.color}) / 0.30)`,
                          }}>
                          <Globe size={9} />
                          {s.domain}
                          <ExternalLink size={9} />
                        </a>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {claims.length > LIMIT && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="w-full border-t border-hairline px-4 py-2.5 text-[12px] font-medium text-pos transition hover:bg-raised/40">
          {showAll ? "Show fewer" : `Show ${claims.length - LIMIT} more claim${claims.length - LIMIT === 1 ? "" : "s"}`}
        </button>
      )}
    </div>
  );
}
