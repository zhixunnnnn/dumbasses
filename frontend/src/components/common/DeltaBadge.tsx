import { signed } from "../../lib/format";

type Props = {
  delta: number;
  align?: "left" | "right";
};

export default function DeltaBadge({
  delta,
  align = "right",
}: Props) {
  const positive = delta >= 0;
  return (
    <div
      className={`flex flex-col ${
        align === "right" ? "items-end" : "items-start"
      }`}
    >
      <span
        className={`flex items-center gap-1 font-mono text-sm font-medium tabular-nums ${
          positive ? "text-pos" : "text-neg"
        }`}
      >
        <span className="text-[10px]">{positive ? "▲" : "▼"}</span>
        {signed(Math.abs(delta) * (positive ? 1 : -1))}
      </span>
    </div>
  );
}
