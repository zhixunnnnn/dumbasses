import { useState } from "react";
import type { Company, QuadrantKey } from "../../types";
import { QUADRANT_ORDER, QUADRANTS } from "../../lib/quadrant";
import { gradeColor } from "../../theme/tokens";
import {
  IDENTITY,
  PAD,
  PLOT_H,
  PLOT_W,
  VIEW,
  dotRadius,
  quadrantScreenRect,
  scaleX,
  scaleY,
  zoomFor,
} from "./geometry";

type Props = {
  companies: Company[];
  selectedId: string | null;
  onSelect: (company: Company) => void;
};

const TINT = {
  leaders: "#3ecf8e",
  profitFirst: "#e0b24a",
  purposeFirst: "#4cc4d4",
  laggards: "#ec6a5e",
} as const;

export default function ScatterMatrix({
  companies,
  selectedId,
  onSelect,
}: Props) {
  const [active, setActive] = useState<QuadrantKey | null>(null);
  const [hovered, setHovered] = useState<Company | null>(null);
  const zoom = active ? zoomFor(active) : IDENTITY;
  const zoomed = active !== null;

  const groupStyle: React.CSSProperties = {
    transform: `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`,
    transformBox: "view-box",
    transformOrigin: "0 0",
    transition: "transform 0.6s cubic-bezier(0.65,0,0.35,1)",
  };

  const screenOf = (c: Company) => ({
    x: ((zoom.scale * scaleX(c.esgScore) + zoom.tx) / VIEW.w) * 100,
    y: ((zoom.scale * scaleY(c.financialScore) + zoom.ty) / VIEW.h) * 100,
  });

  return (
    <div
      className="relative w-full select-none"
      style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}
      onMouseLeave={() => {
        setActive(null);
        setHovered(null);
      }}
    >
      <svg
        viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
        className="h-full w-full text-white"
        role="img"
        aria-label="ESG versus financial performance matrix"
      >
        <defs>
          <clipPath id="plot-clip">
            <rect x={PAD.left} y={PAD.top} width={PLOT_W} height={PLOT_H} />
          </clipPath>
        </defs>

        <g clipPath="url(#plot-clip)">
          <g style={groupStyle}>
            {QUADRANT_ORDER.map((key) => {
              const r = quadrantScreenRect(key);
              return (
                <rect
                  key={key}
                  x={r.x}
                  y={r.y}
                  width={r.width}
                  height={r.height}
                  fill={TINT[key]}
                  opacity={active === key ? 0.1 : 0.04}
                  style={{ transition: "opacity 0.4s" }}
                />
              );
            })}

            {[10, 20, 30, 40, 50, 60, 70, 80, 90].map((g) => (
              <g key={g} opacity={zoomed ? 0.5 : 1}>
                <line
                  x1={scaleX(g)}
                  y1={PAD.top}
                  x2={scaleX(g)}
                  y2={PAD.top + PLOT_H}
                  stroke="currentColor"
                  strokeOpacity={g === 50 ? 0.16 : 0.05}
                  strokeDasharray={g === 50 ? "5 5" : undefined}
                />
                <line
                  x1={PAD.left}
                  y1={scaleY(g)}
                  x2={PAD.left + PLOT_W}
                  y2={scaleY(g)}
                  stroke="currentColor"
                  strokeOpacity={g === 50 ? 0.16 : 0.05}
                  strokeDasharray={g === 50 ? "5 5" : undefined}
                />
              </g>
            ))}

            <g style={{ pointerEvents: zoomed ? "auto" : "none" }}>
              {companies.map((c) => {
                const isSelected = c.id === selectedId;
                const isHovered = hovered?.id === c.id;
                return (
                  <circle
                    key={c.id}
                    cx={scaleX(c.esgScore)}
                    cy={scaleY(c.financialScore)}
                    r={dotRadius(c.marketCap) / (zoomed ? zoom.scale : 1)}
                    fill={gradeColor[c.grade]}
                    fillOpacity={isHovered || isSelected ? 1 : 0.78}
                    stroke={isHovered || isSelected ? "#ffffff" : "transparent"}
                    strokeWidth={1.4 / zoom.scale}
                    className={zoomed ? "cursor-pointer" : ""}
                    onMouseEnter={() => setHovered(c)}
                    onMouseLeave={() => setHovered(null)}
                    onClick={() => onSelect(c)}
                    style={{ transition: "fill-opacity 0.2s" }}
                  />
                );
              })}
            </g>
          </g>
        </g>

        <rect
          x={PAD.left}
          y={PAD.top}
          width={PLOT_W}
          height={PLOT_H}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.12}
        />

        <g opacity={zoomed ? 0 : 1} style={{ transition: "opacity 0.3s" }}>
          {[0, 25, 50, 75, 100].map((g) => (
            <g key={g}>
              <text
                x={scaleX(g)}
                y={PAD.top + PLOT_H + 16}
                textAnchor="middle"
                className="fill-faint text-[10px]"
              >
                {g}
              </text>
              <text
                x={PAD.left - 8}
                y={scaleY(g) + 3}
                textAnchor="end"
                className="fill-faint text-[10px]"
              >
                {g}
              </text>
            </g>
          ))}
        </g>

        <text
          x={PAD.left + PLOT_W / 2}
          y={VIEW.h - 6}
          textAnchor="middle"
          className="fill-muted text-[11px] font-medium"
        >
          ESG Score →
        </text>
        <text
          x={14}
          y={PAD.top + PLOT_H / 2}
          textAnchor="middle"
          transform={`rotate(-90 14 ${PAD.top + PLOT_H / 2})`}
          className="fill-muted text-[11px] font-medium"
        >
          Financial Performance →
        </text>

        {!zoomed &&
          QUADRANT_ORDER.map((key) => {
            const r = quadrantScreenRect(key);
            const meta = QUADRANTS[key];
            return (
              <g key={key} className="cursor-pointer">
                <text
                  x={r.x + r.width / 2}
                  y={r.y + r.height / 2 - 7}
                  textAnchor="middle"
                  className="text-[19px] font-bold uppercase tracking-[0.12em]"
                  fill={meta.accent}
                  style={{
                    paintOrder: "stroke",
                    stroke: "#0d0c0b",
                    strokeWidth: 5,
                    strokeLinejoin: "round",
                  }}
                >
                  {meta.title}
                </text>
                <text
                  x={r.x + r.width / 2}
                  y={r.y + r.height / 2 + 13}
                  textAnchor="middle"
                  className="text-[11px] font-medium"
                  fill="#b6b1a8"
                  style={{
                    paintOrder: "stroke",
                    stroke: "#0d0c0b",
                    strokeWidth: 4,
                    strokeLinejoin: "round",
                  }}
                >
                  {meta.blurb}
                </text>
                <rect
                  x={r.x}
                  y={r.y}
                  width={r.width}
                  height={r.height}
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
            style={{ background: QUADRANTS[active].accent }}
          />
          <span className="font-semibold text-txt">
            {QUADRANTS[active].title}
          </span>
          <span className="text-faint">· move out to zoom back</span>
        </div>
      )}

      {!zoomed && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg border border-hairline bg-canvas/70 px-3 py-1.5 text-[11px] text-muted backdrop-blur">
          Hover a quadrant to zoom in
        </div>
      )}

      {hovered && zoomed && (
        <div
          className="pointer-events-none absolute z-10 w-44 -translate-x-1/2 -translate-y-[115%] rounded-lg border border-hairline bg-surface px-3 py-2 shadow-float"
          style={{
            left: `${screenOf(hovered).x}%`,
            top: `${screenOf(hovered).y}%`,
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-txt">
              {hovered.ticker}
            </span>
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-bold text-canvas"
              style={{ background: gradeColor[hovered.grade] }}
            >
              {hovered.grade}
            </span>
          </div>
          <p className="truncate text-[11px] text-muted">{hovered.name}</p>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted">
            <span>ESG {hovered.esgScore}</span>
            <span>Fin {hovered.financialScore}</span>
          </div>
          <p className="mt-0.5 text-[10px] text-faint">
            ${hovered.marketCap}B · {hovered.sector}
          </p>
        </div>
      )}
    </div>
  );
}
