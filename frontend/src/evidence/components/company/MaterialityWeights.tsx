import type { RatingScore } from "../../types";
import { PILLAR_COLOR } from "../../lib/ui";

// The SASB material-topic weights that drive the ESG rating (ported from smartass's
// materiality view). Weights are fixed by the SASB Electric Utilities & Power Generators
// standard — the same for every company — so this shows WHAT the score leans on and how
// much each topic actually contributed.
export default function MaterialityWeights({ rating, industry }: { rating: RatingScore; industry: string }) {
  const topics = rating.topic_breakdown ?? [];
  if (!topics.length) return null;
  const maxW = Math.max(...topics.map((t) => t.weight), 1);
  const pillarLabel = (p: "E" | "S" | "G") =>
    p === "E" ? "Environmental" : p === "S" ? "Social" : "Governance";

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <h3 className="text-sm font-semibold text-txt">SASB materiality weights</h3>
      <p className="mt-1 text-[11px] leading-snug text-faint">
        Each material topic scored × its SASB weight, fixed by the{" "}
        <span className="text-muted">{industry}</span> standard (sums to 100%). Environmental
        topics use objective evidence (CDP + Climate TRACE); Social/Governance topics use the
        rating agencies as a reference. Shows which topics the score actually leans on.
      </p>

      {/* weight bars */}
      <div className="mt-3 space-y-1.5">
        {topics.map((t) => (
          <div key={t.topic_id} className="flex items-center gap-2 text-[12px]">
            <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: PILLAR_COLOR[t.pillar] }} />
            <span className="w-32 shrink-0 truncate text-txt" title={`${t.name} · ${pillarLabel(t.pillar)}`}>
              {t.name}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
              <div className="h-full rounded-full"
                style={{ width: `${(t.weight / maxW) * 100}%`, background: PILLAR_COLOR[t.pillar], opacity: 0.75 }} />
            </div>
            <span className="w-10 shrink-0 text-right font-mono text-faint">{t.weight}%</span>
          </div>
        ))}
      </div>

      {/* topic table: weight × agency score = contribution */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-hairline text-faint">
              <th className="py-1 text-left font-medium">Material topic</th>
              <th className="py-1 text-right font-medium">Weight</th>
              <th className="py-1 text-right font-medium">Score</th>
              <th className="py-1 text-right font-medium">Contribution</th>
            </tr>
          </thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t.topic_id} className="border-b border-hairline/50 last:border-0">
                <td className="py-1">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-sm" style={{ background: PILLAR_COLOR[t.pillar] }} />
                    <span className="text-txt">{t.name}</span>
                  </span>
                </td>
                <td className="py-1 text-right font-mono text-muted">{t.weight}%</td>
                <td className="py-1 text-right font-mono text-txt">
                  {t.score == null ? "—" : t.score.toFixed(0)}
                </td>
                <td className="py-1 text-right font-mono text-muted">
                  {t.contribution == null ? "—" : t.contribution.toFixed(1)}
                </td>
              </tr>
            ))}
            <tr className="border-t border-hairline">
              <td className="py-1 font-semibold text-txt" colSpan={3}>ESG rating = Σ (score × weight)</td>
              <td className="py-1 text-right font-mono font-semibold text-txt">
                {rating.total == null ? "—" : rating.total.toFixed(1)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
