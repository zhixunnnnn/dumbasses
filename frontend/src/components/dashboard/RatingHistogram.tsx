import type { Company } from "../../types";
import { gradeDistribution } from "../../data/selectors";
import { gradeColor } from "../../theme/tokens";
import { Histogram } from "../charts";

export default function RatingHistogram({
  companies,
}: {
  companies: Company[];
}) {
  const dist = gradeDistribution(companies);
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        Rating distribution
      </p>
      <div className="mt-4">
        <Histogram
          bars={dist.map((d) => ({
            label: d.grade,
            value: d.count,
            color: gradeColor[d.grade],
          }))}
        />
      </div>
    </section>
  );
}
