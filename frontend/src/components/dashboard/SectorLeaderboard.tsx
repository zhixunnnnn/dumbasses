import type { Company } from "../../types";
import { sectorStats } from "../../data/selectors";

export default function SectorLeaderboard({
  companies,
}: {
  companies: Company[];
}) {
  const stats = sectorStats(companies);
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        Sector ESG leaderboard
      </p>
      <ul className="mt-3 space-y-2.5">
        {stats.map((s) => (
          <li key={s.sector} className="flex items-center gap-3">
            <span className="w-28 shrink-0 truncate text-sm text-muted">
              {s.sector}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
              <div
                className="h-full rounded-full bg-pos/70"
                style={{
                  width: `${s.avgEsg}%`,
                  transition: "width 0.6s cubic-bezier(0.22,1,0.36,1)",
                }}
              />
            </div>
            <span className="w-9 shrink-0 text-right font-mono text-xs tabular-nums text-txt">
              {s.avgEsg.toFixed(0)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
