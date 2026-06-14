import { useMemo } from "react";
import type { MatrixPoint } from "../../types";
import { QUADRANT } from "../../lib/ui";
import { useNavigation } from "../../navigation/NavigationContext";

const W = 680;
const H = 460;
const PAD = { l: 54, r: 18, t: 30, b: 46 };
const X_SPLIT = 50;

export default function MomentumMatrix({ points }: { points: MatrixPoint[] }) {
  const { openCompany } = useNavigation();
  const pts = points.filter((p) => p.x !== null && p.y !== null);

  const yAbs = useMemo(
    () => Math.max(2, ...pts.map((p) => Math.abs(p.y ?? 0))) * 1.25,
    [pts],
  );

  const px = (x: number) => PAD.l + (x / 100) * (W - PAD.l - PAD.r);
  const py = (y: number) => PAD.t + (1 - (y + yAbs) / (2 * yAbs)) * (H - PAD.t - PAD.b);
  const r = (size: number | null) => 5 + ((size ?? 60) - 50) / 50 * 6;

  const cx0 = px(X_SPLIT);
  const cy0 = py(0);

  const quadRects: { q: keyof typeof QUADRANT; x: number; y: number; w: number; h: number }[] = [
    { q: "HIDDEN_WINNERS", x: PAD.l, y: PAD.t, w: cx0 - PAD.l, h: cy0 - PAD.t },
    { q: "FUTURE_LEADERS", x: cx0, y: PAD.t, w: W - PAD.r - cx0, h: cy0 - PAD.t },
    { q: "VALUE_TRAPS", x: PAD.l, y: cy0, w: cx0 - PAD.l, h: H - PAD.b - cy0 },
    { q: "OVERRATED", x: cx0, y: cy0, w: W - PAD.r - cx0, h: H - PAD.b - cy0 },
  ];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="ESG Momentum Matrix">
      {quadRects.map((q) => (
        <g key={q.q}>
          <rect x={q.x} y={q.y} width={q.w} height={q.h}
            fill={QUADRANT[q.q].color} fillOpacity={0.05} />
          <text x={q.x + 10} y={q.y + 18} className="text-[11px] font-semibold"
            fill={QUADRANT[q.q].color} fillOpacity={0.85}>
            {QUADRANT[q.q].emoji} {QUADRANT[q.q].label}
          </text>
        </g>
      ))}

      {/* split lines */}
      <line x1={cx0} x2={cx0} y1={PAD.t} y2={H - PAD.b} stroke="white" strokeOpacity={0.12} strokeDasharray="3 3" />
      <line x1={PAD.l} x2={W - PAD.r} y1={cy0} y2={cy0} stroke="white" strokeOpacity={0.18} />

      {/* axes labels */}
      <text x={(PAD.l + W - PAD.r) / 2} y={H - 12} textAnchor="middle" className="fill-faint text-[11px]">
        Rater consensus today  (low&nbsp; →&nbsp; high)
      </text>
      <text x={16} y={(PAD.t + H - PAD.b) / 2} textAnchor="middle" className="fill-faint text-[11px]"
        transform={`rotate(-90 16 ${(PAD.t + H - PAD.b) / 2})`}>
        Evidence momentum  (declining → improving)
      </text>

      {pts.map((p) => {
        const x = px(p.x as number);
        const y = py(p.y as number);
        const color = p.quadrant ? QUADRANT[p.quadrant].color : "#9a968e";
        return (
          <g key={p.id} className="cursor-pointer" onClick={() => openCompany(p.id)}>
            {p.is_underpriced_improver && (
              <circle cx={x} cy={y} r={r(p.size) + 5} fill="none" stroke={color} strokeOpacity={0.5}>
                <animate attributeName="r" values={`${r(p.size) + 3};${r(p.size) + 8};${r(p.size) + 3}`}
                  dur="2.4s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={x} cy={y} r={r(p.size)} fill={color} fillOpacity={0.85} stroke="white" strokeOpacity={0.15}>
              <title>{p.name} · consensus {p.x} · momentum {p.y}</title>
            </circle>
            <text x={x} y={y - r(p.size) - 4} textAnchor="middle" className="fill-txt text-[10px] font-medium">
              {p.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
