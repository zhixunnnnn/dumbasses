import type { SeriesPoint } from "../../types";

/** Change in the verified-evidence total over each horizon, as bars diverging from
 *  a zero baseline. A single "momentum per year" number hides whether the gain was
 *  steady or a one-off jump; one row per horizon shows it. */
export default function MomentumBars({ series }: { series: SeriesPoint[] }) {
  const pts = series.filter((s): s is SeriesPoint & { total: number } => s.total !== null);
  if (pts.length < 2) return null;

  const latest = pts[pts.length - 1];
  const horizons = [1, 2, 3]
    .map((back) => {
      const prior = pts[pts.length - 1 - back];
      return prior ? { label: `${back}y`, from: prior.year, delta: latest.total - prior.total } : null;
    })
    .filter((h): h is { label: string; from: number; delta: number } => h !== null);

  const first = pts[0];
  if (first.year !== latest.year && !horizons.some((h) => h.from === first.year)) {
    horizons.push({
      label: `since ${first.year}`,
      from: first.year,
      delta: latest.total - first.total,
    });
  }
  if (!horizons.length) return null;

  const max = Math.max(...horizons.map((h) => Math.abs(h.delta)), 1);

  return (
    <div className="mt-3 space-y-1">
      {horizons.map((h) => {
        const pct = (Math.abs(h.delta) / max) * 50; // half-width: bars grow from the centre
        const up = h.delta >= 0;
        return (
          <div key={h.label} className="flex items-center gap-2">
            <span className="w-[68px] shrink-0 text-[11px] text-muted">{h.label}</span>
            <span className="w-[52px] shrink-0 text-right font-mono text-[11px]"
              style={{ color: `rgb(var(--color-${up ? "pos" : "neg"}))` }}>
              {up ? "+" : ""}{h.delta.toFixed(1)}
            </span>
            <span className="relative h-2.5 flex-1 rounded bg-canvas/50">
              <span className="absolute inset-y-0 left-1/2 w-px bg-hairline" />
              <span
                className="absolute inset-y-0 rounded"
                style={{
                  left: up ? "50%" : `${50 - pct}%`,
                  width: `${pct}%`,
                  backgroundColor: `rgb(var(--color-${up ? "pos" : "neg"}) / 0.75)`,
                }}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}
