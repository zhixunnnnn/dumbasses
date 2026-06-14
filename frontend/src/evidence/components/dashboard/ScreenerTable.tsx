import { useState } from "react";
import { ArrowUpDown } from "lucide-react";
import type { CompanyRow } from "../../types";
import { na, signed } from "../../lib/ui";
import { QuadrantBadge } from "../common/badges";
import { useNavigation } from "../../navigation/NavigationContext";

type Key = "evidence_total" | "consensus" | "divergence" | "evidence_gap" | "momentum" | "compliance_score" | "forecast";

const COLS: { key: Key; label: string; hint: string; lowerBetter?: boolean }[] = [
  { key: "evidence_total", label: "Evidence", hint: "Verified evidence score (0–100)" },
  { key: "consensus", label: "Consensus", hint: "Rater consensus percentile" },
  { key: "divergence", label: "Divergence", hint: "Rater disagreement — higher = less trust", lowerBetter: true },
  { key: "evidence_gap", label: "Gap", hint: "Evidence percentile − consensus" },
  { key: "momentum", label: "Momentum", hint: "Evidence-score slope / yr" },
  { key: "compliance_score", label: "Compl. gap", hint: "Fraction of in-force regs missing", lowerBetter: true },
  { key: "forecast", label: "Forecast", hint: "Predicted next-yr evidence (HYPOTHESIS)" },
];

export default function ScreenerTable({ rows }: { rows: CompanyRow[] }) {
  const { openCompany } = useNavigation();
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: "evidence_gap", desc: true });
  const [improversOnly, setImproversOnly] = useState(false);

  const filtered = improversOnly ? rows.filter((r) => r.is_underpriced_improver) : rows;
  const sorted = [...filtered].sort((a, b) => {
    const av = a[sort.key];
    const bv = b[sort.key];
    if (av === null) return 1;
    if (bv === null) return -1;
    return sort.desc ? bv - av : av - bv;
  });

  const toggle = (key: Key) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }));

  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex items-center justify-between px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-txt">Screener</h3>
          <p className="text-[11px] text-faint">Sortable. Click any row to drill to the receipts.</p>
        </div>
        <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted">
          <input type="checkbox" checked={improversOnly}
            onChange={(e) => setImproversOnly(e.target.checked)}
            className="accent-pos" />
          Underpriced Improvers only
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="border-y border-hairline text-faint">
              <th className="px-4 py-2 text-left font-medium">Company</th>
              <th className="px-3 py-2 text-left font-medium">Quadrant</th>
              {COLS.map((c) => (
                <th key={c.key} title={c.hint}
                  className="cursor-pointer px-3 py-2 text-right font-medium hover:text-txt"
                  onClick={() => toggle(c.key)}>
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    <ArrowUpDown size={11} className={sort.key === c.key ? "text-pos" : "opacity-40"} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id}
                onClick={() => openCompany(r.id)}
                className="cursor-pointer border-b border-hairline/60 transition hover:bg-raised/50">
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    {r.is_underpriced_improver && <span className="h-1.5 w-1.5 rounded-full bg-pos" />}
                    <div>
                      <p className="font-medium text-txt">{r.name}</p>
                      <p className="font-mono text-[10px] text-faint">{r.ticker} · {r.sector}</p>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5"><QuadrantBadge q={r.quadrant} /></td>
                <td className="px-3 py-2.5 text-right font-mono text-txt">{na(r.evidence_total)}</td>
                <td className="px-3 py-2.5 text-right font-mono text-muted">{na(r.consensus)}</td>
                <td className="px-3 py-2.5 text-right font-mono"
                  style={{ color: r.divergence === null ? undefined : r.divergence > 33 ? "#ec6a5e" : "#9a968e" }}>
                  {na(r.divergence)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono"
                  style={{ color: r.evidence_gap === null ? undefined : r.evidence_gap > 0 ? "#3ecf8e" : "#9a968e" }}>
                  {signed(r.evidence_gap)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono"
                  style={{ color: r.momentum === null ? undefined : r.momentum > 0 ? "#3ecf8e" : "#ec6a5e" }}>
                  {signed(r.momentum)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-muted">
                  {r.compliance_score === null ? "N.A." : `${Math.round(r.compliance_score * 100)}%`}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-profit">{na(r.forecast)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
