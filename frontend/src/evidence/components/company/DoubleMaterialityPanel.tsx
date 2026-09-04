import { GitCompareArrows } from "lucide-react";
import type { DoubleMateriality } from "../../types";

const FIN = "#4cc4d4";   // financial materiality (ESG rating)
const IMP = "#3ecf8e";   // impact materiality (carbon intensity)
const GW = "#ec6a5e";    // greenwashing penalty
const fmt = (v: number | null | undefined, d = 0) => (v == null ? "—" : v.toFixed(d));

export default function DoubleMaterialityPanel({ dm }: { dm?: DoubleMateriality | null }) {
  if (!dm) return null;
  const curve = (x1: number, y1: number, x2: number, y2: number) =>
    `M${x1},${y1} C ${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center gap-2">
        <GitCompareArrows size={15} className="text-purpose" />
        <h3 className="text-sm font-semibold text-txt">Double materiality — ESRS composite</h3>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-faint">
        One score fusing both lenses: <span style={{ color: FIN }}>financial materiality</span> (how the
        market prices ESG into the company) blended {Math.round(dm.weight_financial * 100)}/
        {Math.round(dm.weight_impact * 100)} with <span style={{ color: IMP }}>impact materiality</span>{" "}
        (the company&apos;s real carbon intensity), minus a{" "}
        <span style={{ color: GW }}>greenwashing</span> penalty.
      </p>

      {/* flow diagram */}
      <div className="mt-2 overflow-x-auto">
        <svg viewBox="0 0 720 220" className="w-full" style={{ minWidth: 560 }} role="img"
          aria-label="Double-materiality composite flow">
          <defs>
            <marker id="dm-ah" markerWidth="7" markerHeight="7" refX="5.5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#9a968e" />
            </marker>
          </defs>

          {/* financial box */}
          <g>
            <path d={curve(228, 52, 470, 92)} fill="none" stroke="rgb(var(--color-hairline))" strokeWidth={1.4} />
            <rect x={8} y={24} width={220} height={56} rx={7} fill="rgb(var(--color-canvas))" stroke="rgb(var(--color-hairline))" />
            <rect x={8} y={24} width={4} height={56} rx={2} fill={FIN} />
            <text x={22} y={44} fontSize={10.5} fill="rgb(var(--color-muted))">Financial materiality · ESG rating</text>
            <text x={22} y={68} fontSize={20} fontWeight={700} fill="rgb(var(--color-txt))">{fmt(dm.financial, 1)}</text>
            <text x={216} y={57} fontSize={11} fill={FIN} textAnchor="end" fontWeight={700}>
              × {Math.round(dm.weight_financial * 100)}%
            </text>
          </g>

          {/* impact box */}
          <g>
            <path d={curve(228, 168, 470, 128)} fill="none" stroke="rgb(var(--color-hairline))" strokeWidth={1.4} />
            <rect x={8} y={140} width={220} height={56} rx={7} fill="rgb(var(--color-canvas))" stroke="rgb(var(--color-hairline))" />
            <rect x={8} y={140} width={4} height={56} rx={2} fill={IMP} />
            <text x={22} y={160} fontSize={10.5} fill="rgb(var(--color-muted))">Impact materiality · carbon intensity</text>
            <text x={22} y={184} fontSize={20} fontWeight={700} fill="rgb(var(--color-txt))">
              {dm.impact == null ? "N.A." : fmt(dm.impact, 0)}
            </text>
            <text x={216} y={173} fontSize={11} fill={IMP} textAnchor="end" fontWeight={700}>
              × {Math.round(dm.weight_impact * 100)}%
            </text>
          </g>

          {/* blend arrows */}
          <path d={curve(470, 92, 512, 96)} fill="none" stroke="#9a968e" strokeWidth={1.5} markerEnd="url(#dm-ah)" />
          <path d={curve(470, 128, 512, 116)} fill="none" stroke="#9a968e" strokeWidth={1.5} markerEnd="url(#dm-ah)" />
          {dm.greenwashing_penalty > 0 && (
            <text x={604} y={64} fontSize={11} fill={GW} textAnchor="middle" fontWeight={700}>
              − {fmt(dm.greenwashing_penalty, 1)} greenwashing
            </text>
          )}

          {/* composite */}
          <rect x={516} y={74} width={196} height={92} rx={10}
            fill="color-mix(in srgb, rgb(var(--color-pos)) 10%, rgb(var(--color-canvas)))" stroke="rgb(var(--color-pos))" strokeWidth={1.5} />
          <text x={614} y={98} fontSize={11} fill="rgb(var(--color-muted))" textAnchor="middle">Double-materiality score</text>
          <text x={614} y={140} fontSize={34} fontWeight={800} fill="rgb(var(--color-txt))" textAnchor="middle">
            {dm.composite == null ? "N.A." : fmt(dm.composite, 1)}
          </text>
        </svg>
      </div>

      {/* carbon intensity + greenwashing detail */}
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-hairline bg-canvas/40 p-3">
          <p className="text-[11px] font-medium text-muted">Carbon intensity</p>
          <p className="mt-0.5 font-mono text-sm text-txt">
            {dm.carbon_intensity == null ? "N.A." : `${fmt(dm.carbon_intensity, 1)} tCO₂e / $M`}
          </p>
          <p className="text-[10px] text-faint">
            {dm.intensity_rank != null
              ? `#${dm.intensity_rank} of ${dm.intensity_peers} — ${dm.intensity_rank === 1 ? "cleanest" : dm.intensity_rank === dm.intensity_peers ? "most carbon-intensive" : "mid-pack"} per $ invested`
              : dm.under_attributed
                ? "Climate TRACE under-attributes this owner — impact excluded to avoid crowning a data gap"
                : "no emissions/market-cap match — impact is N.A."}
          </p>
        </div>
        <div className="rounded-lg border border-hairline bg-canvas/40 p-3">
          <p className="text-[11px] font-medium text-muted">
            Greenwashing penalty · {fmt(dm.greenwashing_penalty, 1)} pts
          </p>
          {dm.greenwashing_drivers.length === 0 ? (
            <p className="mt-0.5 text-[11px] text-faint">
              No gap — the ESG rating is in line with the company&apos;s real impact, and no
              controversy headlines surfaced.
            </p>
          ) : (
            <ul className="mt-1 space-y-1">
              {dm.greenwashing_drivers.map((d, i) => (
                <li key={i} className="text-[11px] leading-snug text-faint">
                  <span className="font-medium" style={{ color: GW }}>−{d.points}</span>{" "}
                  <span className="text-muted">{d.label}:</span> {d.detail}
                </li>
              ))}
            </ul>
          )}
          {dm.greenwashing_headlines && dm.greenwashing_headlines.length > 0 && (
            <div className="mt-2 border-t border-hairline pt-2">
              <p className="text-[10px] font-medium uppercase tracking-wide text-faint">
                Reality check · web controversies
              </p>
              <ul className="mt-1 space-y-1">
                {dm.greenwashing_headlines.slice(0, 4).map((h, i) => (
                  <li key={i} className="text-[11px] leading-snug">
                    <a href={h.url} target="_blank" rel="noreferrer"
                      className="text-txt underline-offset-2 hover:text-pos hover:underline">
                      {h.title}
                    </a>
                    {h.source && <span className="text-faint"> · {h.source}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      {dm.note && <p className="mt-2 text-[10px] leading-snug text-faint">{dm.note}</p>}
    </div>
  );
}
