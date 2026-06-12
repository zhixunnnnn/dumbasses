import type { Metric } from "../../types";

type Props = {
  data: Metric[];
  color?: string;
  height?: number;
  max?: number;
  valueSuffix?: string;
};

export default function BarChart({
  data,
  color = "#3ecf8e",
  height = 150,
  max = 100,
  valueSuffix = "",
}: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 items-end gap-3" style={{ minHeight: height }}>
        {data.map((d) => (
          <div
            key={d.label}
            className="flex flex-1 flex-col items-center justify-end gap-1"
          >
            <span className="text-xs font-medium text-muted">
              {d.value}
              {valueSuffix}
            </span>
            <div
              className="w-full rounded-t-md"
              style={{
                height: `${(d.value / max) * (height - 28)}px`,
                background: color,
                opacity: 0.85,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3">
        {data.map((d) => (
          <span
            key={d.label}
            className="flex-1 truncate text-center text-[11px] text-faint"
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}
