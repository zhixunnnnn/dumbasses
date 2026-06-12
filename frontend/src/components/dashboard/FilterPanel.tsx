import { useMemo, useState } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import type { Company, ESGGrade, QuadrantKey } from "../../types";
import {
  activeFilterCount,
  capBounds,
  defaultFilters,
  toggleIn,
  type Filters,
  type MomentumFilter,
} from "../../lib/filters";
import { SECTOR_LIST, REGION_LIST } from "../../data/companies";
import { QUADRANT_ORDER, QUADRANTS } from "../../lib/quadrant";
import { gradeColor } from "../../theme/tokens";
import { usdBillions } from "../../lib/format";
import ChipToggle, { type ChipOption } from "../common/ChipToggle";
import Segmented from "../common/Segmented";
import RangeSlider from "../common/RangeSlider";

const GRADES: ESGGrade[] = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"];

type Props = {
  companies: Company[];
  filters: Filters;
  setFilters: (f: Filters) => void;
  resultCount: number;
};

export default function FilterPanel({
  companies,
  filters,
  setFilters,
  resultCount,
}: Props) {
  const [open, setOpen] = useState(false);
  const defaults = useMemo(() => defaultFilters(companies), [companies]);
  const [capMin, capMax] = useMemo(() => capBounds(companies), [companies]);
  const active = activeFilterCount(filters, defaults);

  const patch = (p: Partial<Filters>) => setFilters({ ...filters, ...p });

  const sectorOptions: ChipOption<string>[] = SECTOR_LIST.map((s) => ({
    value: s,
    label: s,
  }));
  const regionOptions: ChipOption<string>[] = REGION_LIST.map((r) => ({
    value: r,
    label: r,
  }));
  const gradeOptions: ChipOption<ESGGrade>[] = GRADES.map((g) => ({
    value: g,
    label: g,
    color: gradeColor[g],
  }));
  const quadrantOptions: ChipOption<QuadrantKey>[] = QUADRANT_ORDER.map((q) => ({
    value: q,
    label: QUADRANTS[q].title,
    color: QUADRANTS[q].accent,
  }));

  const pillarThresholds = [
    { value: 0, label: "Any" },
    { value: 50, label: "50+" },
    { value: 60, label: "60+" },
    { value: 70, label: "70+" },
    { value: 80, label: "80+" },
  ];

  return (
    <div className="rounded-xl border border-hairline bg-surface">
      <div className="flex flex-wrap items-center gap-2 p-3">
        <div className="relative min-w-[180px] flex-1">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            value={filters.search}
            onChange={(e) => patch({ search: e.target.value })}
            placeholder="Search 95 companies…"
            className="w-full rounded-lg border border-hairline bg-canvas py-2 pl-9 pr-3 text-sm outline-none transition focus:border-pos/40"
          />
        </div>

        <button
          onClick={() => setOpen((v) => !v)}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
            open || active
              ? "border-pos/40 bg-pos/10 text-txt"
              : "border-hairline text-muted hover:text-txt"
          }`}
        >
          <SlidersHorizontal size={15} />
          Filters
          {active > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-pos px-1 text-[11px] font-bold text-canvas">
              {active}
            </span>
          )}
        </button>

        <span className="px-1 font-mono text-sm tabular-nums text-muted">
          {resultCount}
        </span>

        {active > 0 && (
          <button
            onClick={() => setFilters(defaultFilters(companies))}
            className="flex items-center gap-1 rounded-lg px-2 py-2 text-sm text-faint transition hover:text-neg"
          >
            <X size={14} /> Reset
          </button>
        )}
      </div>

      {open && (
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 border-t border-hairline p-4 animate-fade-up lg:grid-cols-3">
          <Field label="Sectors">
            <ChipToggle
              options={sectorOptions}
              selected={filters.sectors}
              onToggle={(v) => patch({ sectors: toggleIn(filters.sectors, v) })}
            />
          </Field>
          <Field label="Regions">
            <ChipToggle
              options={regionOptions}
              selected={filters.regions}
              onToggle={(v) => patch({ regions: toggleIn(filters.regions, v) })}
            />
          </Field>
          <Field label="Quadrant">
            <ChipToggle
              options={quadrantOptions}
              selected={filters.quadrants}
              onToggle={(v) =>
                patch({ quadrants: toggleIn(filters.quadrants, v) })
              }
            />
          </Field>

          <Field label="ESG rating">
            <ChipToggle
              options={gradeOptions}
              selected={filters.grades}
              onToggle={(v) => patch({ grades: toggleIn(filters.grades, v) })}
            />
          </Field>
          <Field label="Momentum">
            <Segmented<MomentumFilter>
              options={[
                { value: "all", label: "All" },
                { value: "positive", label: "Gainers" },
                { value: "negative", label: "Decliners" },
              ]}
              value={filters.momentum}
              onChange={(v) => patch({ momentum: v })}
            />
          </Field>
          <Field label="Max controversy">
            <Segmented<number>
              options={[0, 1, 2, 3, 4, 5].map((n) => ({
                value: n,
                label: `${n}`,
              }))}
              value={filters.maxControversy}
              onChange={(v) => patch({ maxControversy: v })}
            />
          </Field>

          <Field label="ESG score">
            <RangeSlider
              label="Range"
              min={0}
              max={100}
              value={filters.esg}
              onChange={(v) => patch({ esg: v })}
            />
          </Field>
          <Field label="Financial score">
            <RangeSlider
              label="Range"
              min={0}
              max={100}
              value={filters.fin}
              onChange={(v) => patch({ fin: v })}
            />
          </Field>
          <Field label="Market cap">
            <RangeSlider
              label="Range"
              min={capMin}
              max={capMax}
              step={10}
              value={filters.cap}
              onChange={(v) => patch({ cap: v })}
              format={usdBillions}
            />
          </Field>

          <Field label="Min environment">
            <Segmented<number>
              options={pillarThresholds}
              value={filters.minE}
              onChange={(v) => patch({ minE: v })}
            />
          </Field>
          <Field label="Min social">
            <Segmented<number>
              options={pillarThresholds}
              value={filters.minS}
              onChange={(v) => patch({ minS: v })}
            />
          </Field>
          <Field label="Min governance">
            <Segmented<number>
              options={pillarThresholds}
              value={filters.minG}
              onChange={(v) => patch({ minG: v })}
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </p>
      {children}
    </div>
  );
}
