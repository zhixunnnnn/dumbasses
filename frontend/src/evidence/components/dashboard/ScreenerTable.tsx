import { useMemo, useState } from "react";
import { ArrowUpDown, ExternalLink, Scale } from "lucide-react";
import type { CompanyRow, RegQuality, RegulationInfo } from "../../types";
import { na, signed } from "../../lib/ui";
import { api, useApi } from "../../lib/api";
import { QuadrantBadge, RegBadge } from "../common/badges";
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

const STATUSES: ("ANY" | RegQuality)[] = ["ANY", "MET", "PARTIAL", "MISSING", "NA"];

function statusFor(r: CompanyRow, regId: string): RegQuality | null {
  return r.regulations?.find((x) => x.reg_id === regId)?.status ?? null;
}

export default function ScreenerTable({ rows }: { rows: CompanyRow[] }) {
  const { openCompany } = useNavigation();
  const { data: catalog } = useApi(api.regulations, []);
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: "evidence_gap", desc: true });
  const [improversOnly, setImproversOnly] = useState(false);
  const [regId, setRegId] = useState("ALL");
  const [regStatus, setRegStatus] = useState<"ANY" | RegQuality>("ANY");

  // regulation options: prefer the catalog (names + counts), else derive from the rows.
  const regOptions = useMemo<{ reg_id: string; name: string; n?: number }[]>(() => {
    if (catalog?.length) return catalog.map((c) => ({ reg_id: c.reg_id, name: c.name, n: c.n_applicable }));
    const seen = new Map<string, string>();
    rows.forEach((r) => r.regulations?.forEach((x) => seen.set(x.reg_id, x.name)));
    return [...seen].map(([reg_id, name]) => ({ reg_id, name }));
  }, [catalog, rows]);

  const regInfo: RegulationInfo | undefined = catalog?.find((c) => c.reg_id === regId);
  const regActive = regId !== "ALL";

  let filtered = improversOnly ? rows.filter((r) => r.is_underpriced_improver) : rows;
  if (regActive) {
    filtered = filtered.filter((r) => statusFor(r, regId) !== null); // bound by this regime
    if (regStatus !== "ANY") filtered = filtered.filter((r) => statusFor(r, regId) === regStatus);
  }

  const sorted = [...filtered].sort((a, b) => {
    const av = a[sort.key];
    const bv = b[sort.key];
    if (av === null) return 1;
    if (bv === null) return -1;
    return sort.desc ? bv - av : av - bv;
  });

  const toggle = (key: Key) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }));

  const selectReg = (id: string) => {
    setRegId(id);
    setRegStatus("ANY");
  };

  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-txt">Screener</h3>
          <p className="text-[11px] text-faint">
            Sortable. Filter by regulation to see who each regime binds. Click any row for the receipts.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-lg border border-hairline bg-canvas/50 px-2 py-1">
            <Scale size={13} className="text-purpose" />
            <select
              value={regId}
              onChange={(e) => selectReg(e.target.value)}
              className="max-w-[230px] bg-transparent text-[12px] text-txt focus:outline-none"
            >
              <option value="ALL">All regulations</option>
              {regOptions.map((o) => (
                <option key={o.reg_id} value={o.reg_id}>
                  {o.name}{o.n != null ? ` (${o.n})` : ""}
                </option>
              ))}
            </select>
          </div>
          {regActive && (
            <div className="flex rounded-lg border border-hairline bg-canvas/40 p-0.5">
              {STATUSES.map((s) => (
                <button key={s} onClick={() => setRegStatus(s)}
                  className={`rounded-md px-2 py-0.5 text-[11px] transition ${
                    regStatus === s ? "bg-raised text-txt" : "text-muted hover:text-txt"
                  }`}>
                  {s === "ANY" ? "Any" : s}
                </button>
              ))}
            </div>
          )}
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted">
            <input type="checkbox" checked={improversOnly}
              onChange={(e) => setImproversOnly(e.target.checked)}
              className="accent-pos" />
            Improvers only
          </label>
        </div>
      </div>

      {regActive && regInfo && (
        <div className="border-t border-hairline bg-canvas/30 px-4 py-2.5 text-[11px] leading-snug text-muted">
          <p>{regInfo.requirement}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-faint">
            <span>Effective <span className="text-muted">{regInfo.effective_year}</span></span>
            <span>Binds <span className="text-muted">{regInfo.applies_to}</span></span>
            <span><span className="text-muted">{regInfo.n_applicable}</span> of {rows.length} screened</span>
            <span className="text-faint">
              {regInfo.n_met > 0 && <span className="text-pos">{regInfo.n_met} MET </span>}
              {regInfo.n_partial > 0 && <span style={{ color: "#e0b24a" }}>· {regInfo.n_partial} PARTIAL </span>}
              {regInfo.n_missing > 0 && <span className="text-neg">· {regInfo.n_missing} MISSING </span>}
              {regInfo.n_na > 0 && <span>· {regInfo.n_na} N.A.</span>}
            </span>
            {regInfo.n_scraped > 0 && (
              <span className="text-pos" title="Companies verified against their published report (live)">
                {regInfo.n_scraped} live-verified
              </span>
            )}
            {regInfo.source_url && (
              <a href={regInfo.source_url} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 text-muted underline-offset-2 hover:text-pos hover:underline">
                regulation source <ExternalLink size={10} />
              </a>
            )}
          </p>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="border-y border-hairline text-faint">
              <th className="px-4 py-2 text-left font-medium">Company</th>
              <th className="px-3 py-2 text-left font-medium">Quadrant</th>
              {regActive && <th className="px-3 py-2 text-left font-medium">Status</th>}
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
            {sorted.length === 0 && (
              <tr>
                <td colSpan={regActive ? COLS.length + 3 : COLS.length + 2}
                  className="px-4 py-8 text-center text-[12px] text-faint">
                  No companies match this filter.
                </td>
              </tr>
            )}
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
                {regActive && (
                  <td className="px-3 py-2.5">
                    {statusFor(r, regId) ? <RegBadge status={statusFor(r, regId)!} /> : <span className="text-faint">—</span>}
                  </td>
                )}
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
