import { CheckCircle2, Users, Minus, AlertTriangle } from "lucide-react";
import type { SeriesPoint, Witness } from "../../types";
import { signed } from "../../lib/ui";
import Why from "../common/Why";

const W = 920;
const H = 320;
const PAD = { l: 44, r: 44, t: 16, b: 40 };

const PIN_META: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  emissions_verified: { color: "#3ecf8e", icon: CheckCircle2 },
  hiring_surge: { color: "#4cc4d4", icon: Users },
  rater_unchanged: { color: "#9a968e", icon: Minus },
  controversy: { color: "#ec6a5e", icon: AlertTriangle },
};

export default function PriceWitness({ witness, series }: { witness: Witness; series: SeriesPoint[] }) {
  const candles = witness.candles;
  if (candles.length === 0) return <p className="text-sm text-faint">No price data.</p>;

  const dates = candles.map((c) => c.week_date);
  const xIndex = (d: string) => {
    let lo = 0, hi = dates.length - 1;
    // nearest date by string compare (ISO sorts correctly)
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (dates[mid] < d) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };
  const xAt = (i: number) => PAD.l + (i / (candles.length - 1)) * (W - PAD.l - PAD.r);
  const xDate = (d: string) => xAt(xIndex(d));

  // price axis (company candles + rebased STI)
  const base0 = candles[0].close;
  const bench0 = witness.benchmark[0]?.close ?? 1;
  const benchRebased = witness.benchmark.map((b) => (base0 * b.close) / bench0);
  const lows = candles.map((c) => c.low);
  const highs = candles.map((c) => c.high);
  const pmin = Math.min(...lows, ...benchRebased);
  const pmax = Math.max(...highs, ...benchRebased);
  const pspan = pmax - pmin || 1;
  const yPrice = (v: number) => PAD.t + (1 - (v - pmin) / pspan) * (H - PAD.t - PAD.b);

  // evidence axis (0..100) on the right
  const yEv = (v: number) => PAD.t + (1 - v / 100) * (H - PAD.t - PAD.b);
  const evPts = series.filter((s) => s.total !== null)
    .map((s) => ({ x: xDate(`${s.year}-12-31`), y: yEv(s.total as number), total: s.total as number, year: s.year }));

  const slot = (W - PAD.l - PAD.r) / candles.length;
  const flat = witness.flat;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {/* rising-evidence band shading */}
        {witness.band.map((b, i) => {
          const x0 = xDate(b.start_date);
          const x1 = xDate(b.end_date);
          return (
            <g key={i}>
              <rect x={x0} y={PAD.t} width={Math.max(2, x1 - x0)} height={H - PAD.t - PAD.b}
                fill="#3ecf8e" fillOpacity={0.07} />
              <line x1={x0} y1={yEv(b.start_score)} x2={x1} y2={yEv(b.end_score)}
                stroke="#3ecf8e" strokeOpacity={0.35} strokeWidth={1.5} strokeDasharray="2 2" />
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
          return (
            <g key={c.week_date} opacity={0.92}>
              <line x1={x} x2={x} y1={yPrice(c.high)} y2={yPrice(c.low)} stroke={color} strokeWidth={0.6} />
              <rect x={x - slot * 0.3} y={top} width={Math.max(0.8, slot * 0.6)}
                height={Math.max(0.6, bot - top)} fill={color} />
            </g>
          );
        })}

        {/* rebased STI benchmark */}
        <polyline fill="none" stroke="#9a968e" strokeOpacity={0.55} strokeWidth={1.2} strokeDasharray="4 3"
          points={benchRebased.map((v, i) => `${xAt(i)},${yPrice(v)}`).join(" ")} />

        {/* evidence line (right axis) */}
        <polyline fill="none" stroke="#4cc4d4" strokeWidth={2}
          points={evPts.map((p) => `${p.x},${p.y}`).join(" ")} />
        {evPts.map((p) => (
          <circle key={p.year} cx={p.x} cy={p.y} r={3} fill="#4cc4d4">
            <title>Evidence {p.year}: {p.total}</title>
          </circle>
        ))}

        {/* pins on the bottom axis */}
        {witness.pins.map((pin, i) => {
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

        {/* right-axis evidence ticks */}
        {[0, 50, 100].map((v) => (
          <text key={v} x={W - PAD.r + 6} y={yEv(v) + 3} className="fill-purpose text-[9px]">{v}</text>
        ))}
        <text x={W - PAD.r + 6} y={PAD.t - 4} className="fill-purpose text-[9px]">evidence</text>
        {/* year ticks */}
        {evPts.map((p) => (
          <text key={`yr${p.year}`} x={p.x} y={H - 8} textAnchor="middle" className="fill-faint text-[9px]">{p.year}</text>
        ))}
      </svg>

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
        Weekly candles · STI rebased (dashed) · evidence score on the right axis. A witness, not an
        oracle — it shows the gap, it does not predict returns. No technical indicators.
      </p>
    </div>
  );
}
