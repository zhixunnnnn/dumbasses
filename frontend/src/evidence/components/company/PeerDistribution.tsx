// Bloomberg-style peer distribution: where this company's evidence score sits
// within its sector — or, when the sector has no scored peers in the panel,
// within the whole screened panel so the card always has a comparison.
import { na } from "../../lib/ui";

type Peer = { id: string; name: string; evidence_total: number | null };
type PanelRow = { id: string; name: string; evidence_total: number | null };

const BINS = Array.from({ length: 10 }, (_, i) => ({
  lo: i * 10,
  hi: i === 9 ? 101 : (i + 1) * 10,
  label: `${i * 10}`,
}));

export default function PeerDistribution({
  self,
  selfId,
  selfName,
  peers,
  sector,
  panel,
}: {
  self: number | null;
  selfId: string;
  selfName: string;
  peers: Peer[];
  sector: string;
  panel: PanelRow[] | null;
}) {
  let scope = sector;
  let cohort = [
    { name: selfName, score: self, isSelf: true },
    ...peers.map((p) => ({ name: p.name, score: p.evidence_total, isSelf: false })),
  ].filter((c): c is { name: string; score: number; isSelf: boolean } => c.score != null);

  // Lone company in its sector: rank it against the whole screened panel instead.
  if (cohort.length < 2 && panel) {
    const fallback = panel
      .map((r) => ({ name: r.name, score: r.evidence_total, isSelf: r.id === selfId }))
      .filter((c): c is { name: string; score: number; isSelf: boolean } => c.score != null);
    if (fallback.length >= 2) {
      cohort = fallback;
      scope = "all screened companies";
    }
  }

  if (cohort.length < 2) {
    return <p className="mt-2 text-[11px] text-faint">Not enough scored companies to draw a distribution.</p>;
  }

  const binOf = (score: number) => BINS.findIndex((b) => score >= b.lo && score < b.hi);
  const counts = BINS.map((_, i) => cohort.filter((c) => binOf(c.score) === i));
  const max = Math.max(1, ...counts.map((c) => c.length));
  const selfBin = self != null ? binOf(self) : -1;
  const rank = self != null ? cohort.filter((c) => c.score > self).length + 1 : null;
  const wideCohort = cohort.length > 4;

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
      {/* a big fallback cohort would make the name list taller than the card — the
          bars' hover titles still name everyone, so list names only for small cohorts */}
      {!wideCohort && (
        <div className="mt-2 space-y-1">
          {[...cohort].sort((a, b) => b.score - a.score).map((c) => (
            <div key={c.name} className="flex items-center justify-between text-[11px]">
              <span className={c.isSelf ? "font-semibold text-pos" : "text-muted"}>{c.name}</span>
              <span className="font-mono tabular-nums text-txt">{na(c.score)}</span>
            </div>
          ))}
        </div>
      )}
      {rank !== null && (
        <p className="mt-1.5 text-[11px] text-faint">
          #{rank} of {cohort.length} in {scope} · evidence score
        </p>
      )}
    </div>
  );
}
