type Props = {
  label: string;
  min: number;
  max: number;
  step?: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
  format?: (value: number) => string;
};

export default function RangeSlider({
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
  format = (v) => `${v}`,
}: Props) {
  const [lo, hi] = value;
  const span = max - min || 1;
  const loPct = ((lo - min) / span) * 100;
  const hiPct = ((hi - min) / span) * 100;

  const setLo = (raw: number) => onChange([Math.min(raw, hi - step), hi]);
  const setHi = (raw: number) => onChange([lo, Math.max(raw, lo + step)]);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-muted">{label}</span>
        <span className="font-mono text-[11px] tabular-nums text-txt">
          {format(lo)} – {format(hi)}
        </span>
      </div>
      <div className="relative h-4">
        <div className="absolute top-1/2 h-1 w-full -translate-y-1/2 rounded-full bg-raised" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-pos/60"
          style={{ left: `${loPct}%`, right: `${100 - hiPct}%` }}
        />
        <input
          type="range"
          className="dual"
          min={min}
          max={max}
          step={step}
          value={lo}
          onChange={(e) => setLo(Number(e.target.value))}
          aria-label={`${label} minimum`}
        />
        <input
          type="range"
          className="dual"
          min={min}
          max={max}
          step={step}
          value={hi}
          onChange={(e) => setHi(Number(e.target.value))}
          aria-label={`${label} maximum`}
        />
      </div>
    </div>
  );
}
