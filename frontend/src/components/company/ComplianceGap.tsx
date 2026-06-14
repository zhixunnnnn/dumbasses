import type { Compliance } from "../../types";
import { RegBadge } from "../common/badges";
import Why from "../common/Why";

export default function ComplianceGap({ compliance }: { compliance: Compliance }) {
  const all = [
    ...compliance.met,
    ...compliance.partial,
    ...compliance.missing,
    ...compliance.not_in_force,
  ];
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-txt">Regulatory compliance gap</h3>
          <p className="text-[11px] text-faint">SGX · ISSB · MAS · ASEAN Taxonomy</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-lg font-semibold"
            style={{ color: (compliance.score ?? 0) > 0 ? "#e0b24a" : "#3ecf8e" }}>
            {compliance.score === null ? "N.A." : `${Math.round(compliance.score * 100)}%`}
          </span>
          <Why trace={compliance.trace} title="Compliance gap" />
        </div>
      </div>
      <div className="mt-3 space-y-1.5">
        {all.map((r) => (
          <div key={r.reg_id} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="truncate text-muted">{r.name}</span>
            <RegBadge status={r.status} />
          </div>
        ))}
      </div>
      <p className="mt-3 text-[10.5px] leading-snug text-faint">
        A regulation not yet in force (e.g. ISSB S2, effective 2025) is a readiness gap — never a violation.
        Unknown status is excluded, never counted as missing.
      </p>
    </div>
  );
}
