import type { Company } from "../../types";
import { regionStats } from "../../data/selectors";
import { usdBillions } from "../../lib/format";
import { Donut } from "../charts";

const REGION_COLORS: Record<string, string> = {
  "North America": "#3ecf8e",
  Europe: "#4cc4d4",
  "Asia-Pacific": "#a78bfa",
  "Latin America": "#e0b24a",
  "Middle East": "#e87f4a",
  Africa: "#ec6a5e",
};

export default function RegionBreakdown({
  companies,
}: {
  companies: Company[];
}) {
  const stats = regionStats(companies);
  const totalCap = stats.reduce((s, r) => s + r.cap, 0);
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        Capital by region
      </p>
      <div className="mt-4">
        <Donut
          segments={stats.map((r) => ({
            label: r.region,
            value: r.cap,
            color: REGION_COLORS[r.region] ?? "#9a968e",
          }))}
          centerValue={usdBillions(totalCap)}
          centerLabel="total"
        />
      </div>
    </section>
  );
}
