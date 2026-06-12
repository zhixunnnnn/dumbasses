import { signedPercent, percent } from "../../lib/format";

type Props = {
  delta: number;
  deviation?: number;
  align?: "left" | "right";
};

export default function DeltaBadge({
  delta,
  deviation,
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
        {signedPercent(Math.abs(delta) * (positive ? 1 : -1))}
      </span>
      {deviation !== undefined && (
        <span className="font-mono text-[11px] tabular-nums text-faint">
          ±{percent(deviation)}
        </span>
      )}
    </div>
  );
}
