import { useMemo, useState } from "react";
import { CheckCircle2, Users, Minus, AlertTriangle } from "lucide-react";
import type { SeriesPoint, Witness } from "../../types";
import { signed } from "../../lib/ui";
import Why from "../common/Why";

const W = 920;
const H = 340;
const PAD = { l: 52, r: 46, t: 14, b: 38 };

const PIN_META: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  emissions_verified: { color: "#3ecf8e", icon: CheckCircle2 },
  hiring_surge: { color: "#4cc4d4", icon: Users },
  rater_unchanged: { color: "#9a968e", icon: Minus },
  controversy: { color: "#ec6a5e", icon: AlertTriangle },
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let v = start; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(4)));
  return out;
}

export default function PriceWitness({ witness, series }: { witness: Witness; series: SeriesPoint[] }) {
  const all = witness.candles;
  const minDate = all[0]?.week_date ?? "";
  const maxDate = all[all.length - 1]?.week_date ?? "";
  const years = useMemo(() => [...new Set(all.map((c) => c.week_date.slice(0, 4)))], [all]);

  const [from, setFrom] = useState(minDate);
  const [to, setTo] = useState(maxDate);
  const [hover, setHover] = useState<number | null>(null);

  const candles = useMemo(
    () => all.filter((c) => c.week_date >= from && c.week_date <= to),
    [all, from, to],
  );

  if (all.length === 0) return <p className="text-sm text-faint">No price data.</p>;

  const n = candles.length;
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const xAt = (i: number) => PAD.l + (n <= 1 ? 0.5 : i / (n - 1)) * plotW;

  // nearest visible index by ISO date (sorts correctly as strings)
  const xIndex = (d: string) => {
    if (n === 0) return 0;
    let lo = 0, hi = n - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (candles[mid].week_date < d) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };
  const xDate = (d: string) => xAt(xIndex(d));
  const inView = (d: string) => d >= candles[0]?.week_date && d <= candles[n - 1]?.week_date;

  // price axis (company candles + rebased STI over the visible window)
  const base0 = candles[0]?.close ?? 1;
  const benchView = witness.benchmark.filter((b) => b.week_date >= from && b.week_date <= to);
  const bench0 = benchView[0]?.close ?? 1;
  const benchRebased = benchView.map((b) => ({ d: b.week_date, v: (base0 * b.close) / bench0 }));
  const pmin = Math.min(...candles.map((c) => c.low), ...benchRebased.map((b) => b.v));
  const pmax = Math.max(...candles.map((c) => c.high), ...benchRebased.map((b) => b.v));
  const pspan = pmax - pmin || 1;
  const yPrice = (v: number) => PAD.t + (1 - (v - pmin) / pspan) * plotH;

  const yEv = (v: number) => PAD.t + (1 - v / 100) * plotH;
  const evPts = series
    .filter((s) => s.total !== null && inView(`${s.year}-12-31`))
    .map((s) => ({ x: xDate(`${s.year}-12-31`), y: yEv(s.total as number), total: s.total as number, year: s.year }));

  const slot = plotW / Math.max(n, 1);
  const flat = witness.flat;
  const priceTicks = niceTicks(pmin, pmax, 5);

  // x-axis ticks: per-year for long ranges, per-month otherwise
  const spanDays = (Date.parse(candles[n - 1]?.week_date) - Date.parse(candles[0]?.week_date)) / 86400000;
  const byYear = spanDays > 400;
  const xticks: { x: number; label: string }[] = [];
  let prevKey = "";
  candles.forEach((c, i) => {
    const key = byYear ? c.week_date.slice(0, 4) : c.week_date.slice(0, 7);
    if (key !== prevKey) {
      const m = Number(c.week_date.slice(5, 7)) - 1;
      xticks.push({ x: xAt(i), label: byYear ? c.week_date.slice(0, 4) : MONTHS[m] });
      prevKey = key;
    }
  });

  const hc = hover !== null && hover >= 0 && hover < n ? candles[hover] : null;
  const presetCls = (active: boolean) =>
    `rounded-md px-2 py-0.5 text-[11px] transition ${active ? "bg-raised text-txt" : "text-muted hover:text-txt"}`;
  const setRange = (a: string, b: string) => { setFrom(a); setTo(b); setHover(null); };

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const vx = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((vx - PAD.l) / plotW) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };

  return (
    <div>
      {/* date-range filter */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-hairline bg-canvas/40 p-0.5">
          <button className={presetCls(from === minDate && to === maxDate)}
            onClick={() => setRange(minDate, maxDate)}>All</button>
          {years.map((y) => (
            <button key={y} className={presetCls(from === `${y}-01-01` && to === `${y}-12-31`)}
              onClick={() => setRange(`${y}-01-01`, `${y}-12-31`)}>{y}</button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted">
          <input type="date" value={from} min={minDate} max={to}
            onChange={(e) => { setFrom(e.target.value); setHover(null); }}
            className="rounded-md border border-hairline bg-canvas/60 px-1.5 py-0.5 text-txt" />
          <span className="text-faint">→</span>
          <input type="date" value={to} min={from} max={maxDate}
            onChange={(e) => { setTo(e.target.value); setHover(null); }}
            className="rounded-md border border-hairline bg-canvas/60 px-1.5 py-0.5 text-txt" />
        </div>
      </div>

      {n === 0 ? (
        <p className="py-10 text-center text-sm text-faint">No candles in this range.</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
          {/* price gridlines + left axis labels */}
          {priceTicks.map((v) => (
            <g key={`g${v}`}>
              <line x1={PAD.l} x2={W - PAD.r} y1={yPrice(v)} y2={yPrice(v)}
                stroke="#ffffff" strokeOpacity={0.06} strokeWidth={1} />
              <text x={PAD.l - 6} y={yPrice(v) + 3} textAnchor="end" className="fill-faint text-[9px]">{v}</text>
            </g>
          ))}
          <text x={PAD.l - 6} y={PAD.t - 3} textAnchor="end" className="fill-faint text-[9px]">price</text>

          {/* rising-evidence band (clipped to the visible window) */}
          {witness.band.map((b, i) => {
            const s = b.start_date < from ? from : b.start_date;
            const e = b.end_date > to ? to : b.end_date;
            if (e < candles[0].week_date || s > candles[n - 1].week_date) return null;
            const x0 = xDate(s);
            const x1 = xDate(e);
            const full = b.start_date >= from && b.end_date <= to;
            return (
              <g key={i}>
                <rect x={x0} y={PAD.t} width={Math.max(2, x1 - x0)} height={plotH}
                  fill="#3ecf8e" fillOpacity={0.07} />
                {full && (
                  <line x1={x0} y1={yEv(b.start_score)} x2={x1} y2={yEv(b.end_score)}
                    stroke="#3ecf8e" strokeOpacity={0.35} strokeWidth={1.5} strokeDasharray="2 2" />
                )}
              </g>
            );
          })}

          {/* candles */}
          {candles.map((c, i) => {
            const up = c.close >= c.open;
            const color = up ? "#3ecf8e" : "#ef6f63";
            const x = xAt(i);
            const top = yPrice(Math.max(c.open, c.close));
            const bot = yPrice(Math.min(c.open, c.close));
            const bw = Math.max(1, Math.min(10, slot * 0.62));
            return (
              <g key={c.week_date} opacity={hover === null || hover === i ? 0.95 : 0.5}>
                <line x1={x} x2={x} y1={yPrice(c.high)} y2={yPrice(c.low)} stroke={color}
                  strokeWidth={Math.max(0.6, bw * 0.16)} />
                <rect x={x - bw / 2} y={top} width={bw} height={Math.max(0.8, bot - top)} fill={color} />
              </g>
            );
          })}

          {/* rebased STI benchmark */}
          <polyline fill="none" stroke="#9a968e" strokeOpacity={0.55} strokeWidth={1.2} strokeDasharray="4 3"
            points={benchRebased.map((b) => `${xDate(b.d)},${yPrice(b.v)}`).join(" ")} />

          {/* evidence line (right axis) */}
          <polyline fill="none" stroke="#4cc4d4" strokeWidth={2}
            points={evPts.map((p) => `${p.x},${p.y}`).join(" ")} />
          {evPts.map((p) => (
            <circle key={p.year} cx={p.x} cy={p.y} r={3} fill="#4cc4d4">
              <title>Evidence {p.year}: {p.total}</title>
            </circle>
          ))}

          {/* pins on the bottom axis (within range) */}
          {witness.pins.filter((p) => inView(p.date)).map((pin, i) => {
            const meta = PIN_META[pin.type];
            return (
              <g key={i}>
                <line x1={xDate(pin.date)} x2={xDate(pin.date)} y1={H - PAD.b} y2={H - PAD.b + 5}
                  stroke={meta.color} strokeWidth={1} />
                <circle cx={xDate(pin.date)} cy={H - PAD.b + 9} r={2.6} fill={meta.color}>
                  <title>{pin.label}</title>
                </circle>
              </g>
            );
          })}

          {/* right-axis evidence ticks + x ticks */}
          {[0, 50, 100].map((v) => (
            <text key={v} x={W - PAD.r + 6} y={yEv(v) + 3} className="fill-purpose text-[9px]">{v}</text>
          ))}
          <text x={W - PAD.r + 6} y={PAD.t - 3} className="fill-purpose text-[9px]">evidence</text>
          {xticks.map((t, i) => (
            <text key={i} x={t.x} y={H - 6} textAnchor="middle" className="fill-faint text-[9px]">{t.label}</text>
          ))}

          {/* crosshair + OHLC tooltip */}
          {hc && (
            <g pointerEvents="none">
              <line x1={xAt(hover as number)} x2={xAt(hover as number)} y1={PAD.t} y2={H - PAD.b}
                stroke="#ffffff" strokeOpacity={0.18} strokeWidth={1} />
              {(() => {
                const tx = Math.min(Math.max(xAt(hover as number) + 8, PAD.l), W - PAD.r - 150);
                const up = hc.close >= hc.open;
                return (
                  <g transform={`translate(${tx}, ${PAD.t + 4})`}>
                    <rect width="150" height="62" rx="6" fill="#11130f" fillOpacity={0.92}
                      stroke="#2a2c26" strokeWidth={1} />
                    <text x="8" y="16" className="fill-muted text-[10px]">{hc.week_date}</text>
                    <text x="8" y="31" className="text-[10px]" fill="#9a968e">O {hc.open.toFixed(2)}  H {hc.high.toFixed(2)}</text>
                    <text x="8" y="45" className="text-[10px]" fill="#9a968e">L {hc.low.toFixed(2)}</text>
                    <text x="58" y="45" className="text-[10px]" fill={up ? "#3ecf8e" : "#ef6f63"}>C {hc.close.toFixed(2)}</text>
                  </g>
                );
              })()}
            </g>
          )}

          {/* hover capture overlay */}
          <rect x={PAD.l} y={PAD.t} width={plotW} height={plotH} fill="transparent"
            onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
        </svg>
      )}

      <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px] text-faint">
        <span className="inline-flex items-center gap-1"><span className="h-0.5 w-3" style={{ backgroundColor: "#3ecf8e" }} />price (weekly)</span>
        <span className="inline-flex items-center gap-1"><span className="h-0.5 w-3 border-t border-dashed" style={{ borderColor: "#9a968e" }} />STI rebased</span>
        <span className="inline-flex items-center gap-1"><span className="h-0.5 w-3" style={{ backgroundColor: "#4cc4d4" }} />evidence (right axis)</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline bg-canvas/40 px-3 py-2">
        <p className="text-[12px] text-muted">
          Over the verified-improvement window the stock returned{" "}
          <span className="font-mono text-txt">{signed(flat.stock_return)}%</span> vs STI{" "}
          <span className="font-mono text-txt">{signed(flat.sti_return)}%</span> →{" "}
          <span className="font-mono" style={{ color: (flat.rel_return ?? 0) <= 0 ? "#3ecf8e" : "#9a968e" }}>
            {signed(flat.rel_return)}% relative
          </span>
          .{" "}
          {flat.is_flat ? (
            <span className="text-pos">The market has not priced the improvement.</span>
          ) : (
            <span className="text-faint">The market has already reacted.</span>
          )}
        </p>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {witness.pins.slice(0, 8).map((pin, i) => {
          const meta = PIN_META[pin.type];
          const Icon = meta.icon;
          return (
            <span key={i}
              className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-surface px-2 py-1 text-[11px] text-muted">
              <Icon size={12} style={{ color: meta.color }} />
              {pin.label}
              <Why trace={pin.trace_ref} title={pin.label} />
            </span>
          );
        })}
      </div>
      <p className="mt-2 text-[10.5px] text-faint">
        Weekly candles · hover for date &amp; OHLC · filter the range above. A witness, not an oracle —
        it shows the gap, it does not predict returns. No technical indicators.
      </p>
    </div>
  );
}
