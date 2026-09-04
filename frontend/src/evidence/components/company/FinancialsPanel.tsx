import { TrendingUp } from "lucide-react";
import type { CompanyFundamentals } from "../../types";

// ---- formatters -----------------------------------------------------------
const pct = (x: number | null | undefined, d = 1) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`;
const rat = (x: number | null | undefined, d = 2) =>
  x === null || x === undefined ? "—" : x.toFixed(d);
const money = (x: number | null | undefined, cur = "") =>
  x === null || x === undefined ? "—" : `${x.toFixed(2)}${cur ? " " + cur : ""}`;
function compact(x: number | null | undefined, cur = ""): string {
  if (x === null || x === undefined) return "—";
  const a = Math.abs(x);
  const s = a >= 1e12 ? `${(x / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(x / 1e9).toFixed(2)}B`
    : a >= 1e6 ? `${(x / 1e6).toFixed(2)}M` : a >= 1e3 ? `${(x / 1e3).toFixed(1)}K` : x.toFixed(0);
  return cur ? `${s} ${cur}` : s;
}

const RECO_LABEL: Record<string, string> = {
  strong_buy: "Strong Buy", buy: "Buy", hold: "Hold", underperform: "Underperform",
  sell: "Sell", none: "No coverage",
};
const RECO_COLOR: Record<string, string> = {
  strong_buy: "#3ecf8e", buy: "#3ecf8e", hold: "#e0b24a",
  underperform: "#ec6a5e", sell: "#ec6a5e", none: "#9a968e",
};

function Row({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  const color = tone === undefined || tone === null ? undefined : tone >= 0 ? "#3ecf8e" : "#ec6a5e";
  return (
    <tr className="border-b border-hairline/60 last:border-0">
      <td className="py-1 text-[12px] text-muted">{label}</td>
      <td className="py-1 text-right font-mono text-[12px] text-txt" style={{ color }}>{value}</td>
    </tr>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-faint">{title}</p>
      <table className="w-full"><tbody>{children}</tbody></table>
    </div>
  );
}

export default function FinancialsPanel({ f }: { f?: CompanyFundamentals | null }) {
  if (!f) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
        <h3 className="text-sm font-semibold text-txt">Financials &amp; valuation</h3>
        <p className="mt-2 text-[12px] text-faint">No market data available for this listing — N.A.</p>
      </div>
    );
  }
  const fi = f.financials, v = f.valuation, r = f.ratings, cur = fi.currency ?? "";
  const reco = r.recommendation ?? "none";
  const upside = r.target_mean != null && r.current_price ? r.target_mean / r.current_price - 1 : null;
  const dist = r.distribution;
  const segs = dist
    ? [
        { k: "Strong Buy", n: dist.strongBuy, c: "#2e9e6b" },
        { k: "Buy", n: dist.buy, c: "#3ecf8e" },
        { k: "Hold", n: dist.hold, c: "#e0b24a" },
        { k: "Sell", n: dist.sell, c: "#ec6a5e" },
        { k: "Strong Sell", n: dist.strongSell, c: "#c0392b" },
      ].filter((s) => (s.n ?? 0) > 0)
    : [];
  const distTotal = segs.reduce((a, s) => a + (s.n ?? 0), 0);

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center gap-2">
        <TrendingUp size={15} className="text-profit" />
        <h3 className="text-sm font-semibold text-txt">Financials &amp; valuation</h3>
        <span className="text-[10px] text-faint">Yahoo Finance · live</span>
      </div>

      {/* CGS headline: price · analyst target · implied upside · consensus */}
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-faint">Price</p>
          <p className="font-mono text-lg font-semibold text-txt">{money(r.current_price, cur)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-faint">Analyst target</p>
          <p className="font-mono text-lg font-semibold text-txt">{money(r.target_mean, cur)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-faint">Implied upside</p>
          <p className="font-mono text-lg font-semibold"
            style={{ color: upside == null ? undefined : upside >= 0 ? "#3ecf8e" : "#ec6a5e" }}>
            {upside == null ? "—" : `${upside >= 0 ? "+" : ""}${(upside * 100).toFixed(0)}%`}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-faint">Consensus</p>
          <p className="text-lg font-semibold" style={{ color: RECO_COLOR[reco] }}>
            {RECO_LABEL[reco] ?? reco}
          </p>
          <p className="text-[10px] text-faint">{r.n_analysts ?? 0} analysts</p>
        </div>
      </div>

      {/* analyst distribution bar */}
      {distTotal > 0 && (
        <div className="mt-3">
          <div className="flex h-2 overflow-hidden rounded-full">
            {segs.map((s) => (
              <div key={s.k} title={`${s.k}: ${s.n}`}
                style={{ width: `${((s.n ?? 0) / distTotal) * 100}%`, background: s.c }} />
            ))}
          </div>
          <p className="mt-1 text-[10px] text-faint">
            {segs.map((s) => `${s.n} ${s.k}`).join(" · ")}
          </p>
        </div>
      )}

      {/* ratio blocks */}
      <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
        <Block title="Valuation">
          <Row label="Market cap" value={fi.market_cap_fmt ?? compact(fi.market_cap, cur)} />
          <Row label="Enterprise value" value={compact(fi.enterprise_value, cur)} />
          <Row label="P/E (trailing)" value={rat(v.trailing_pe)} />
          <Row label="P/E (forward)" value={rat(v.forward_pe)} />
          <Row label="Price / book" value={rat(v.price_to_book)} />
          <Row label="EV / EBITDA" value={rat(v.ev_to_ebitda)} />
          <Row label="Beta" value={rat(v.beta)} />
        </Block>
        <Block title="Profitability">
          <Row label="Revenue (ttm)" value={fi.revenue_fmt ?? compact(fi.revenue, cur)} />
          <Row label="Revenue growth" value={pct(fi.revenue_growth)} tone={fi.revenue_growth} />
          <Row label="Operating margin" value={pct(fi.operating_margin)} tone={fi.operating_margin} />
          <Row label="Net margin" value={pct(fi.profit_margin)} tone={fi.profit_margin} />
          <Row label="Return on equity" value={pct(fi.roe)} tone={fi.roe} />
          <Row label="Debt / equity" value={fi.debt_to_equity != null ? `${rat(fi.debt_to_equity, 1)}%` : "—"} />
        </Block>
        <Block title="Per share & dividend">
          <Row label="EPS (ttm)" value={money(v.eps_trailing, cur)} />
          <Row label="Dividend / share" value={money(v.dividend_rate, cur)} />
          <Row label="Dividend yield" value={pct(v.dividend_yield)} tone={v.dividend_yield ? 1 : null} />
          <Row label="Payout ratio" value={pct(v.payout_ratio)} />
          <Row label="52-wk high" value={money(v.fifty_two_high, cur)} />
          <Row label="52-wk low" value={money(v.fifty_two_low, cur)} />
        </Block>
      </div>
    </div>
  );
}
