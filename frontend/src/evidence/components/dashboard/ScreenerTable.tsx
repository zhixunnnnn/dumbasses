import { useMemo, useState } from "react";
import { ArrowUpDown, ExternalLink, Scale } from "lucide-react";
import type { CompanyRow, RegQuality, RegulationInfo } from "../../types";
import type { Provenance } from "../../types";
import { na, signed, NA_REASON, PROVENANCE, PROVENANCE_MARK } from "../../lib/ui";
import { api, useApi } from "../../lib/api";
import { QuadrantBadge, RegBadge } from "../common/badges";
import { useNavigation } from "../../navigation/NavigationContext";

type Key = "rating_total" | "divergence";

// Trimmed to the investor essentials, all REAL: the ESG rating and how contested it is
// (divergence = trust, real-only). Finance columns (Last / Chg % / Trend) sit before these.
// The illustrative surfaces (consensus, evidence, compliance, MSCI forecast) are gone.
const COLS: { key: Key; label: string; hint: string; lowerBetter?: boolean }[] = [
  { key: "rating_total", label: "ESG Rating", hint: "ESG rating (0–100): Environmental from CDP + Climate TRACE, Social/Governance from real rating agencies. SASB-material-weighted. N.A. when no real input." },
  { key: "divergence", label: "Divergence", hint: "Real rater disagreement — higher = less trust. N.A. unless computed from real ratings only.", lowerBetter: true },
];

const STATUSES: ("ANY" | RegQuality)[] = ["ANY", "MET", "PARTIAL", "MISSING", "NA"];

function statusFor(r: CompanyRow, regId: string): RegQuality | null {
  return r.regulations?.find((x) => x.reg_id === regId)?.status ?? null;
}

export default function ScreenerTable({ rows }: { rows: CompanyRow[] }) {
  const { navigate } = useNavigation();
  const { data: catalog } = useApi(api.regulations, []);
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: "rating_total", desc: true });
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
              <th className="px-3 py-2 text-right font-medium" title="Last close (local currency)">Last</th>
              <th className="px-3 py-2 text-right font-medium" title="Last weekly price change">Chg %</th>
              <th className="px-3 py-2 text-right font-medium" title="Recent close-price trend">Trend</th>
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
                <td colSpan={(regActive ? COLS.length + 3 : COLS.length + 2) + 3}
                  className="px-4 py-8 text-center text-[12px] text-faint">
                  No companies match this filter.
                </td>
              </tr>
            )}
            {sorted.map((r) => (
              <tr key={r.id}
                onClick={() => navigate({ name: "evidenceCompany", id: r.id })}
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
                <td className="px-3 py-2.5 text-right font-mono text-txt">{r.price == null ? "—" : r.price.toFixed(2)}</td>
                <td className="px-3 py-2.5 text-right font-mono"
                  style={{ color: r.price_chg == null ? undefined : r.price_chg >= 0 ? "#3ecf8e" : "#ec6a5e" }}>
                  {r.price_chg == null ? "—" : `${r.price_chg >= 0 ? "+" : ""}${r.price_chg.toFixed(1)}%`}
                </td>
                <td className="px-3 py-2.5"><Sparkline data={r.spark ?? []} /></td>
                <td className="px-3 py-2.5 text-right font-mono text-txt"
                  title={r.rating_provenance ? PROVENANCE[r.rating_provenance].hint : undefined}>
                  {na(r.rating_total)}
                  <ProvMark p={r.rating_provenance} />
                </td>
                {/* Divergence is real-only (N.A. unless computed from real ratings). */}
                <td className="px-3 py-2.5 text-right font-mono"
                  title={r.divergence === null ? "N.A. — needs 2+ real ratings" : undefined}
                  style={{ color: r.divergence === null ? undefined : r.divergence > 33 ? "#ec6a5e" : "#9a968e" }}>
                  {na(r.divergence)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


/** Tiny inline price-trend sparkline (last ~24 weekly closes), green up / red down. */
function Sparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return <span className="text-faint">—</span>;
  const w = 56, h = 16, min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / span) * h}`)
    .join(" ");
  const up = data[data.length - 1] >= data[0];
  return (
    <svg width={w} height={h} className="inline-block align-middle" aria-hidden>
      <polyline points={pts} fill="none" stroke={up ? "#3ecf8e" : "#ec6a5e"} strokeWidth={1.2} />
    </svg>
  );
}


/** A one-character provenance mark for dense table cells: nothing for a fully real
 *  figure, ° when illustrative data contributed, ~ when it is all illustrative. */
function ProvMark({ p }: { p?: Provenance | null }) {
  if (!p || p === "real") return null;
  return (
    <span className="ml-0.5 align-super text-[9px]" style={{ color: PROVENANCE[p].color }}>
      {PROVENANCE_MARK[p]}
    </span>
  );
}
