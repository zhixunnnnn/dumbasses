// Bloomberg-style peer distribution: where this company's evidence score sits
// within its sector. Built entirely from the company payload (self + peers).
import { na } from "../../lib/ui";

type Peer = { id: string; name: string; evidence_total: number | null };

const BINS = Array.from({ length: 10 }, (_, i) => ({
  lo: i * 10,
  hi: i === 9 ? 101 : (i + 1) * 10,
  label: `${i * 10}`,
}));

export default function PeerDistribution({
  self,
  selfName,
  peers,
  sector,
}: {
  self: number | null;
  selfName: string;
  peers: Peer[];
  sector: string;
}) {
  const cohort = [
    { name: selfName, score: self, isSelf: true },
    ...peers.map((p) => ({ name: p.name, score: p.evidence_total, isSelf: false })),
  ].filter((c): c is { name: string; score: number; isSelf: boolean } => c.score != null);

  if (cohort.length < 2) {
    return <p className="mt-2 text-[11px] text-faint">Not enough sector peers with a scored profile to draw a distribution.</p>;
  }

  const binOf = (score: number) => BINS.findIndex((b) => score >= b.lo && score < b.hi);
  const counts = BINS.map((_, i) => cohort.filter((c) => binOf(c.score) === i));
  const max = Math.max(1, ...counts.map((c) => c.length));
  const selfBin = self != null ? binOf(self) : -1;
  const rank = self != null ? cohort.filter((c) => c.score > self).length + 1 : null;

  return (
    <div className="mt-2">
      <div className="flex items-end gap-[3px]" style={{ height: 76 }}>
        {BINS.map((b, i) => {
          const isSelfBin = i === selfBin;
          const members = counts[i];
          return (
            <div key={b.label} className="flex h-full flex-1 flex-col items-center justify-end gap-1"
              title={members.length ? members.map((m) => `${m.name} · ${m.score.toFixed(1)}`).join("\n") : undefined}>
              {isSelfBin && <span className="h-2 w-px border-l border-dashed border-pos" />}
              <div
                className={`w-full rounded-t ${isSelfBin ? "bg-pos/80" : "bg-[#4cc4d4]/55"}`}
                style={{ height: `${(members.length / max) * 48}px`, minHeight: members.length ? 4 : 1 }}
              />
              <span className="text-[9px] leading-none text-faint">{b.label}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 space-y-1">
        {[...cohort].sort((a, b) => b.score - a.score).map((c) => (
          <div key={c.name} className="flex items-center justify-between text-[11px]">
            <span className={c.isSelf ? "font-semibold text-pos" : "text-muted"}>{c.name}</span>
            <span className="font-mono tabular-nums text-txt">{na(c.score)}</span>
          </div>
        ))}
      </div>
      {rank !== null && (
        <p className="mt-1.5 text-[11px] text-faint">
          #{rank} of {cohort.length} in {sector} · evidence score
        </p>
      )}
    </div>
  );
}
