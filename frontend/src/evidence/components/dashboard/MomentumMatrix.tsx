import { useMemo, useState, type CSSProperties } from "react";
import type { MatrixPoint, QuadrantKey } from "../../types";
import { QUADRANT } from "../../lib/ui";
import { useNavigation } from "../../navigation/NavigationContext";

const W = 820;
const H = 600;
const PAD = { l: 54, r: 22, t: 28, b: 52 };
const X_SPLIT = 50;

const ORDER: QuadrantKey[] = [
  "HIDDEN_WINNERS",
  "FUTURE_LEADERS",
  "VALUE_TRAPS",
  "OVERRATED",
];

type Rect = {
  q: QuadrantKey;
  x: number;
  y: number;
  w: number;
  h: number;
};

type Zoom = { scale: number; tx: number; ty: number };

const IDENTITY: Zoom = { scale: 1, tx: 0, ty: 0 };

export default function MomentumMatrix({ points }: { points: MatrixPoint[] }) {
  const { navigate } = useNavigation();
  const [active, setActive] = useState<QuadrantKey | null>(null);
  const [hovered, setHovered] = useState<MatrixPoint | null>(null);

  const pts = points.filter((p) => p.x !== null && p.y !== null);
  const yAbs = useMemo(
    () => Math.max(2, ...pts.map((p) => Math.abs(p.y ?? 0))) * 1.25,
    [pts],
  );

  const px = (x: number) => PAD.l + (x / 100) * (W - PAD.l - PAD.r);
  const py = (y: number) =>
    PAD.t + (1 - (y + yAbs) / (2 * yAbs)) * (H - PAD.t - PAD.b);
  const radius = (size: number | null) => 5 + (((size ?? 60) - 50) / 50) * 6;

  const cx0 = px(X_SPLIT);
  const cy0 = py(0);
  const quadRects: Rect[] = [
    { q: "HIDDEN_WINNERS", x: PAD.l, y: PAD.t, w: cx0 - PAD.l, h: cy0 - PAD.t },
    { q: "FUTURE_LEADERS", x: cx0, y: PAD.t, w: W - PAD.r - cx0, h: cy0 - PAD.t },
    { q: "VALUE_TRAPS", x: PAD.l, y: cy0, w: cx0 - PAD.l, h: H - PAD.b - cy0 },
    { q: "OVERRATED", x: cx0, y: cy0, w: W - PAD.r - cx0, h: H - PAD.b - cy0 },
  ];

  const activeRect = active
    ? quadRects.find((rect) => rect.q === active)
    : undefined;
  const zoom = activeRect ? zoomFor(activeRect) : IDENTITY;
  const zoomed = active !== null;
  const groupStyle: CSSProperties = {
    transform: `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`,
    transformBox: "view-box",
    transformOrigin: "0 0",
    transition: "transform 0.6s cubic-bezier(0.65,0,0.35,1)",
  };

  const screenOf = (point: MatrixPoint) => ({
    x: ((zoom.scale * px(point.x as number) + zoom.tx) / W) * 100,
    y: ((zoom.scale * py(point.y as number) + zoom.ty) / H) * 100,
  });

  return (
    <div
      className="relative w-full select-none"
      style={{ aspectRatio: `${W} / ${H}` }}
      onMouseLeave={() => {
        setActive(null);
        setHovered(null);
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full text-txt"
        role="img"
        aria-label="ESG momentum matrix"
      >
        <defs>
          <clipPath id="evidence-matrix-clip">
            <rect
              x={PAD.l}
              y={PAD.t}
              width={W - PAD.l - PAD.r}
              height={H - PAD.t - PAD.b}
            />
          </clipPath>
        </defs>

        <g clipPath="url(#evidence-matrix-clip)">
          <g style={groupStyle}>
            {quadRects.map((rect) => (
              <rect
                key={rect.q}
                x={rect.x}
                y={rect.y}
                width={rect.w}
                height={rect.h}
                fill={QUADRANT[rect.q].color}
                fillOpacity={active === rect.q ? 0.1 : 0.045}
                style={{ transition: "fill-opacity 0.4s" }}
              />
            ))}

            {[0, 25, 50, 75, 100].map((tick) => (
              <line
                key={`x-${tick}`}
                x1={px(tick)}
                x2={px(tick)}
                y1={PAD.t}
                y2={H - PAD.b}
                stroke="currentColor"
                strokeOpacity={tick === X_SPLIT ? 0.16 : 0.055}
                strokeDasharray={tick === X_SPLIT ? "5 5" : undefined}
              />
            ))}
            {[-1, -0.5, 0, 0.5, 1].map((multiplier) => {
              const y = multiplier * yAbs;
              return (
                <line
                  key={`y-${multiplier}`}
                  x1={PAD.l}
                  x2={W - PAD.r}
                  y1={py(y)}
                  y2={py(y)}
                  stroke="currentColor"
                  strokeOpacity={multiplier === 0 ? 0.18 : 0.055}
                  strokeDasharray={multiplier === 0 ? "5 5" : undefined}
                />
              );
            })}

            <g style={{ pointerEvents: zoomed ? "auto" : "none" }}>
              {pts.map((point) => {
                const x = px(point.x as number);
                const y = py(point.y as number);
                const color = point.quadrant
                  ? QUADRANT[point.quadrant].color
                  : "#9a968e";
                const isHovered = hovered?.id === point.id;
                const dotRadius = radius(point.size) / zoom.scale;
                return (
                  <g key={point.id}>
                    {point.is_underpriced_improver && (
                      <circle
                        cx={x}
                        cy={y}
                        r={dotRadius + 5 / zoom.scale}
                        fill="none"
                        stroke={color}
                        strokeOpacity={0.5}
                      >
                        <animate
                          attributeName="r"
                          values={`${dotRadius + 3 / zoom.scale};${dotRadius + 8 / zoom.scale};${dotRadius + 3 / zoom.scale}`}
                          dur="2.4s"
                          repeatCount="indefinite"
                        />
                      </circle>
                    )}
                    <circle
                      cx={x}
                      cy={y}
                      r={dotRadius}
                      fill={color}
                      fillOpacity={isHovered ? 1 : 0.82}
                      stroke={
                        isHovered ? "rgb(var(--color-surface))" : "transparent"
                      }
                      strokeWidth={1.5 / zoom.scale}
                      className="cursor-pointer"
                      onMouseEnter={() => setHovered(point)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() =>
                        navigate({ name: "evidenceCompany", id: point.id })
                      }
                      style={{ transition: "fill-opacity 0.2s" }}
                    />
                  </g>
                );
              })}
            </g>
          </g>
        </g>

        <rect
          x={PAD.l}
          y={PAD.t}
          width={W - PAD.l - PAD.r}
          height={H - PAD.t - PAD.b}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.12}
        />

        <g opacity={zoomed ? 0 : 1} style={{ transition: "opacity 0.3s" }}>
          {[0, 25, 50, 75, 100].map((tick) => (
            <text
              key={`x-label-${tick}`}
              x={px(tick)}
              y={H - PAD.b + 17}
              textAnchor="middle"
              className="fill-faint text-[10px]"
            >
              {tick}
            </text>
          ))}
          {[-yAbs, 0, yAbs].map((tick) => (
            <text
              key={`y-label-${tick}`}
              x={PAD.l - 8}
              y={py(tick) + 3}
              textAnchor="end"
              className="fill-faint text-[10px]"
            >
              {tick.toFixed(1)}
            </text>
          ))}
        </g>

        <text
          x={(PAD.l + W - PAD.r) / 2}
          y={H - 12}
          textAnchor="middle"
          className="fill-muted text-[11px] font-medium"
        >
          Rater consensus today (low to high)
        </text>
        <text
          x={16}
          y={(PAD.t + H - PAD.b) / 2}
          textAnchor="middle"
          className="fill-muted text-[11px] font-medium"
          transform={`rotate(-90 16 ${(PAD.t + H - PAD.b) / 2})`}
        >
          Evidence momentum (declining to improving)
        </text>

        {!zoomed &&
          ORDER.map((key) => {
            const rect = quadRects.find((q) => q.q === key);
            if (!rect) return null;
            const meta = QUADRANT[key];
            return (
              <g key={key} className="cursor-pointer">
                <text
                  x={rect.x + rect.w / 2}
                  y={rect.y + rect.h / 2 - 8}
                  textAnchor="middle"
                  className="text-[17px] font-bold uppercase tracking-[0.12em]"
                  fill={meta.color}
                  style={{
                    paintOrder: "stroke",
                    stroke: "var(--chart-contrast-stroke)",
                    strokeWidth: 5,
                    strokeLinejoin: "round",
                  }}
                >
                  {meta.label}
                </text>
                <text
                  x={rect.x + rect.w / 2}
                  y={rect.y + rect.h / 2 + 13}
                  textAnchor="middle"
                  className="text-[10.5px] font-medium"
                  fill="var(--chart-soft-label)"
                  style={{
                    paintOrder: "stroke",
                    stroke: "var(--chart-contrast-stroke)",
                    strokeWidth: 4,
                    strokeLinejoin: "round",
                  }}
                >
                  {meta.blurb}
                </text>
                <rect
                  x={rect.x}
                  y={rect.y}
                  width={rect.w}
                  height={rect.h}
                  fill="transparent"
                  onMouseEnter={() => setActive(key)}
                />
              </g>
            );
          })}
      </svg>

      {zoomed && active && (
        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-lg border border-hairline bg-canvas/80 px-3 py-1.5 text-xs backdrop-blur animate-fade-up">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: QUADRANT[active].color }}
          />
          <span className="font-semibold text-txt">
            {QUADRANT[active].label}
          </span>
          <span className="text-faint">move out to zoom back</span>
        </div>
      )}

      {!zoomed && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg border border-hairline bg-canvas/70 px-3 py-1.5 text-[11px] text-muted backdrop-blur">
          Hover a quadrant to zoom in
        </div>
      )}

      {hovered && zoomed && (
        <div
          className="pointer-events-none absolute z-10 w-52 -translate-x-1/2 -translate-y-[115%] rounded-lg border border-hairline bg-surface px-3 py-2 shadow-float"
          style={{
            left: `${screenOf(hovered).x}%`,
            top: `${screenOf(hovered).y}%`,
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm font-semibold text-txt">
              {hovered.id}
            </span>
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
              style={{
                color: hovered.quadrant
                  ? QUADRANT[hovered.quadrant].color
                  : "#9a968e",
                backgroundColor: hovered.quadrant
                  ? `${QUADRANT[hovered.quadrant].color}1f`
                  : "#9a968e1f",
              }}
            >
              {hovered.quadrant
                ? QUADRANT[hovered.quadrant].label
                : "Unplaced"}
            </span>
          </div>
          <p className="truncate text-[11px] text-muted">{hovered.name}</p>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted">
            <span>Consensus {formatNumber(hovered.x)}</span>
            <span>Momentum {formatSigned(hovered.y)}</span>
          </div>
          <p className="mt-0.5 text-[10px] text-faint">
            Evidence score {formatNumber(hovered.size)}
          </p>
        </div>
      )}
    </div>
  );
}

function zoomFor(rect: Rect): Zoom {
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const scale = Math.min(plotW / rect.w, plotH / rect.h);
  const cx = rect.x + rect.w / 2;
  const cy = rect.y + rect.h / 2;
  return {
    scale,
    tx: PAD.l + plotW / 2 - scale * cx,
    ty: PAD.t + plotH / 2 - scale * cy,
  };
}

function formatNumber(value: number | null) {
  return value === null ? "N.A." : value.toFixed(1);
}

function formatSigned(value: number | null) {
  if (value === null) return "N.A.";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}
