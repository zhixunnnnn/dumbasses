// Lightweight filter bar for the dashboard — sector, quadrant, and the
// Underpriced-Improver toggle. Filters every panel on the page.
import type { CompanyRow, QuadrantKey } from "../../types";
import { QUADRANT } from "../../lib/ui";

export type DashFilters = {
  sector: string | "ALL";
  quadrant: QuadrantKey | "ALL";
  improversOnly: boolean;
};

export const defaultDashFilters: DashFilters = { sector: "ALL", quadrant: "ALL", improversOnly: false };

export function applyDashFilters(rows: CompanyRow[], f: DashFilters): CompanyRow[] {
  return rows.filter(
    (r) =>
      (f.sector === "ALL" || r.sector === f.sector) &&
      (f.quadrant === "ALL" || r.quadrant === f.quadrant) &&
      (!f.improversOnly || r.is_underpriced_improver),
  );
}

const QUADRANT_KEYS: QuadrantKey[] = ["HIDDEN_WINNERS", "FUTURE_LEADERS", "VALUE_TRAPS", "OVERRATED"];

export function FilterBar({
  rows,
  filters,
  setFilters,
  resultCount,
}: {
  rows: CompanyRow[];
  filters: DashFilters;
  setFilters: (f: DashFilters) => void;
  resultCount: number;
}) {
  const sectors = [...new Set(rows.map((r) => r.sector))].sort();
  const selectCls =
    "rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-[12px] text-txt outline-none transition hover:border-pos/40 focus:border-pos/60";

  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-hairline bg-surface px-4 py-3 shadow-panel">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">Filter</span>

      <select
        value={filters.sector}
        onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
        className={selectCls}
      >
        <option value="ALL">All sectors</option>
        {sectors.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      <select
        value={filters.quadrant}
        onChange={(e) => setFilters({ ...filters, quadrant: e.target.value as DashFilters["quadrant"] })}
        className={selectCls}
      >
        <option value="ALL">All quadrants</option>
        {QUADRANT_KEYS.map((q) => (
          <option key={q} value={q}>
            {QUADRANT[q].label}
          </option>
        ))}
      </select>

      <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-muted">
        <input
          type="checkbox"
          checked={filters.improversOnly}
          onChange={(e) => setFilters({ ...filters, improversOnly: e.target.checked })}
          className="accent-pos"
        />
        Underpriced Improvers
      </label>

      <span className="ml-auto text-[11px] text-faint">{resultCount} in view</span>
      {(filters.sector !== "ALL" || filters.quadrant !== "ALL" || filters.improversOnly) && (
        <button
          onClick={() => setFilters(defaultDashFilters)}
          className="rounded-md px-2 py-1 text-[11px] font-medium text-muted transition hover:bg-raised hover:text-txt"
        >
          Reset
        </button>
      )}
    </div>
  );
}
