import { ArrowRight, TrendingUp } from "lucide-react";
import type { CompanyRow } from "../../types";
import { na, signed } from "../../lib/ui";
import { ImproverPill } from "../common/badges";
import { useNavigation } from "../../navigation/NavigationContext";

export default function ImproverFeed({ rows }: { rows: CompanyRow[] }) {
  const { openCompany } = useNavigation();
  const improvers = rows
    .filter((r) => r.is_underpriced_improver)
    .sort((a, b) => (b.evidence_gap ?? 0) - (a.evidence_gap ?? 0));

  return (
    <div className="flex h-full flex-col rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex items-center gap-2 border-b border-hairline px-4 py-3">
        <TrendingUp size={15} className="text-pos" />
        <div>
          <h3 className="text-sm font-semibold text-txt">Improver Alerts</h3>
          <p className="text-[11px] text-faint">Verified improvement the market hasn't priced</p>
        </div>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {improvers.length === 0 && (
          <p className="px-2 py-6 text-center text-[12px] text-faint">No underpriced improvers right now.</p>
        )}
        {improvers.map((r) => (
          <button key={r.id} onClick={() => openCompany(r.id)}
            className="group w-full rounded-lg border border-hairline bg-canvas/40 p-3 text-left transition hover:border-pos/40">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-txt">{r.name}</p>
                <p className="font-mono text-[10px] text-faint">{r.ticker} · {r.sector}</p>
              </div>
              <ArrowRight size={14} className="shrink-0 text-faint transition group-hover:text-pos" />
            </div>
            <div className="mt-2 flex items-center justify-between">
              <ImproverPill />
              <div className="flex gap-3 font-mono text-[11px]">
                <span title="Evidence gap vs raters" className="text-pos">gap {signed(r.evidence_gap)}</span>
                <span title="Evidence momentum / yr" className="text-muted">mom {na(r.momentum)}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
