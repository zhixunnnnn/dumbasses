import { FlaskConical } from "lucide-react";
import type { QuadrantKey, RegQuality, VerifyState } from "../../types";
import { QUADRANT, REG_COLOR, STATE_COLOR } from "../../lib/ui";

export function HypothesisBadge({ note }: { note?: string }) {
  return (
    <span
      title={note ?? "Not yet backtested on this data"}
      className="inline-flex items-center gap-1 rounded-md border border-profit/40 bg-profit/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-profit"
    >
      <FlaskConical size={10} />
      Hypothesis
    </span>
  );
}

export function StateBadge({ state }: { state: VerifyState }) {
  const color = STATE_COLOR[state];
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color, backgroundColor: `${color}1f` }}
    >
      {state}
    </span>
  );
}

export function RegBadge({ status }: { status: RegQuality }) {
  const color = REG_COLOR[status];
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold"
      style={{ color, backgroundColor: `${color}1f` }}
    >
      {status}
    </span>
  );
}

export function QuadrantBadge({ q }: { q: QuadrantKey | null }) {
  if (!q) return <span className="text-[11px] text-faint">unplaced</span>;
  const meta = QUADRANT[q];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
      style={{ color: meta.color, backgroundColor: `${meta.color}1a` }}
    >
      <span>{meta.emoji}</span>
      {meta.label}
    </span>
  );
}

export function ImproverPill() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-pos/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-pos">
      ● Underpriced Improver
    </span>
  );
}
