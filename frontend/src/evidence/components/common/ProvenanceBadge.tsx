import type { Provenance } from "../../types";
import { PROVENANCE, provenanceDetail } from "../../lib/ui";

/** A small, always-present label saying whether a number was measured or is demo data.
 *  "real" is deliberately quiet; anything with seeded input is visible. */
export default function ProvenanceBadge({
  provenance,
  contributing,
  real,
  className = "",
}: {
  provenance?: Provenance | null;
  contributing?: string[] | null;
  real?: string[] | null;
  className?: string;
}) {
  if (!provenance) return null;
  const meta = PROVENANCE[provenance];
  const detail = provenanceDetail(contributing, real);
  return (
    <span
      title={detail ? `${meta.hint} (${detail})` : meta.hint}
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[9.5px] font-medium ${className}`}
      style={{ borderColor: `${meta.color}66`, color: meta.color }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
      {meta.label}
    </span>
  );
}
