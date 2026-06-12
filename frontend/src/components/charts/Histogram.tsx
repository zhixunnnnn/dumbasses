type Bar = { label: string; value: number; color: string };

type Props = {
  bars: Bar[];
  height?: number;
};

export default function Histogram({ bars, height = 130 }: Props) {
  const max = Math.max(...bars.map((b) => b.value), 1);
  return (
    <div className="flex h-full flex-col">
      <div
        className="flex flex-1 items-end gap-2"
        style={{ minHeight: height }}
      >
        {bars.map((b, i) => (
          <div
            key={b.label}
            className="flex flex-1 flex-col items-center justify-end gap-1.5"
          >
            <span className="font-mono text-[11px] tabular-nums text-muted">
              {b.value}
            </span>
            <div
              className="w-full rounded-t-md"
              style={{
                height: `${(b.value / max) * (height - 28)}px`,
                background: b.color,
                opacity: 0.85,
                transition: "height 0.5s cubic-bezier(0.22,1,0.36,1)",
                transitionDelay: `${i * 40}ms`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        {bars.map((b) => (
          <span
            key={b.label}
            className="flex-1 text-center text-[11px] font-medium text-faint"
          >
            {b.label}
          </span>
        ))}
      </div>
    </div>
  );
}
