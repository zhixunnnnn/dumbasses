// Bloomberg-style peer distribution: where this company's evidence score sits
// within its sector. The panel only holds a handful of real companies per
// sector, so the histogram is padded with ILLUSTRATIVE peers — deterministic
// per company, bell-shaped around the real scores — and labeled as such, the
// same convention the rater figures use.
import { na } from "../../lib/ui";

type Peer = { id: string; name: string; evidence_total: number | null };

const BINS = Array.from({ length: 10 }, (_, i) => ({
  lo: i * 10,
  hi: i === 9 ? 101 : (i + 1) * 10,
  label: `${i * 10}`,
}));

const COHORT_SIZE = 24;

// deterministic PRNG so the same company always renders the same distribution
function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function illustrativePeers(seedKey: string, center: number, count: number): number[] {
  const rand = mulberry32([...seedKey].reduce((a, c) => Math.imul(a, 31) + c.charCodeAt(0), 7) >>> 0);
  const scores: number[] = [];
  for (let i = 0; i < count; i++) {
    // Box–Muller normal, sd 14, clamped away from the extremes
    const z = Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
    scores.push(Math.min(95, Math.max(5, center + z * 14)));
  }
  return scores;
}

export default function PeerDistribution({
  self,
  selfId,
  selfName,
  peers,
  sector,
}: {
  self: number | null;
  selfId: string;
  selfName: string;
  peers: Peer[];
  sector: string;
  panel?: { id: string; name: string; evidence_total: number | null }[] | null;
}) {
  const real = [
    { name: selfName, score: self, isSelf: true },
    ...peers.map((p) => ({ name: p.name, score: p.evidence_total, isSelf: false })),
  ].filter((c): c is { name: string; score: number; isSelf: boolean } => c.score != null);

  if (real.length === 0) {
    return <p className="mt-2 text-[11px] text-faint">No scored profile to place in a distribution.</p>;
  }

  // real peers only — no illustrative padding on a CGS terminal.
  const synth: number[] = [];
  const total = real.length;

  const binOf = (score: number) => BINS.findIndex((b) => score >= b.lo && score < b.hi);
  const realBins = BINS.map((_, i) => real.filter((c) => binOf(c.score) === i));
  const synthBins = BINS.map((_, i) => synth.filter((s) => binOf(s) === i));
  const max = Math.max(1, ...BINS.map((_, i) => realBins[i].length + synthBins[i].length));
  const selfBin = self != null ? binOf(self) : -1;
  const rank = self != null
    ? [...real.map((c) => c.score), ...synth].filter((s) => s > self).length + 1
    : null;

  return (
    <div className="mt-2">
      <div className="flex items-end gap-[3px]" style={{ height: 76 }}>
        {BINS.map((b, i) => {
          const isSelfBin = i === selfBin;
          const count = realBins[i].length + synthBins[i].length;
          const names = realBins[i].map((m) => `${m.name} · ${m.score.toFixed(1)}`);
          if (synthBins[i].length) names.push(`${synthBins[i].length} illustrative peer${synthBins[i].length > 1 ? "s" : ""}`);
          return (
            <div key={b.label} className="flex h-full flex-1 flex-col items-center justify-end gap-1"
              title={names.join("\n") || undefined}>
              {isSelfBin && <span className="h-2 w-px border-l border-dashed border-pos" />}
              <div
                className={`w-full rounded-t ${isSelfBin ? "bg-pos/80" : realBins[i].length ? "bg-[#4cc4d4]/70" : "bg-[#4cc4d4]/30"}`}
                style={{ height: `${(count / max) * 48}px`, minHeight: count ? 4 : 1 }}
              />
              <span className="text-[9px] leading-none text-faint">{b.label}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 space-y-1">
        {[...real].sort((a, b) => b.score - a.score).map((c) => (
          <div key={c.name} className="flex items-center justify-between text-[11px]">
            <span className={c.isSelf ? "font-semibold text-pos" : "text-muted"}>{c.name}</span>
            <span className="font-mono tabular-nums text-txt">{na(c.score)}</span>
          </div>
        ))}
      </div>
      {rank !== null && (
        <p className="mt-1.5 text-[11px] text-faint">
          #{rank} of {total} {sector} peers{peers.length === 0 ? " (no scored sector peers)" : ""} · real ratings only
        </p>
      )}
    </div>
  );
}
