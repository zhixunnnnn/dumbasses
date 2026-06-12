import type { StatSeries } from "../../types";
import { palette } from "../../theme/tokens";
import { Sparkline } from "../charts";
import DeltaBadge from "../common/DeltaBadge";

export default function StatCard({ stat }: { stat: StatSeries }) {
  const positive = stat.delta >= 0;
  const color = positive ? palette.pos : palette.neg;
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
          {stat.label}
        </p>
        <DeltaBadge delta={stat.delta} deviation={stat.deviation} />
      </div>
      <p className="mt-2 font-mono text-2xl font-semibold tracking-tight text-txt">
        {stat.value}
      </p>
      <div className="mt-3 h-10 overflow-hidden">
        <Sparkline data={stat.series} color={color} height={36} />
      </div>
    </div>
  );
}
