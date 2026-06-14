import { palette } from "../../theme/tokens";
import type { Candle } from "../../types";

type Props = {
  candles: Candle[];
  height?: number;
};

export default function CandlestickChart({ candles, height = 240 }: Props) {
  const width = 640;
  const padX = 14;
  const padTop = 12;
  const padBottom = 26;
  const lows = candles.map((c) => c.low);
  const highs = candles.map((c) => c.high);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = max - min || 1;

  const slot = (width - padX * 2) / candles.length;
  const bodyW = Math.max(3, slot * 0.55);
  const cx = (i: number) => padX + slot * i + slot / 2;
  const y = (v: number) =>
    padTop + (1 - (v - min) / span) * (height - padTop - padBottom);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full text-txt"
      role="img"
      aria-label="Candlestick chart"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((g) => {
        const gy = padTop + g * (height - padTop - padBottom);
        const val = max - g * span;
        return (
          <g key={g}>
            <line
              x1={padX}
              x2={width - padX}
              y1={gy}
              y2={gy}
              stroke="currentColor"
              strokeOpacity={0.06}
            />
            <text
              x={width - padX}
              y={gy - 3}
              textAnchor="end"
              className="fill-faint text-[9px]"
            >
              {val.toFixed(0)}
            </text>
          </g>
        );
      })}
      {candles.map((c, i) => {
        const up = c.close >= c.open;
        const color = up ? palette.pos : palette.neg;
        const top = y(Math.max(c.open, c.close));
        const bottom = y(Math.min(c.open, c.close));
        return (
          <g key={c.label}>
            <line
              x1={cx(i)}
              x2={cx(i)}
              y1={y(c.high)}
              y2={y(c.low)}
              stroke={color}
              strokeWidth={1.2}
            />
            <rect
              x={cx(i) - bodyW / 2}
              y={top}
              width={bodyW}
              height={Math.max(1.5, bottom - top)}
              rx={1}
              fill={color}
              fillOpacity={up ? 0.9 : 0.85}
            >
              <title>
                {c.label} · O {c.open} H {c.high} L {c.low} C {c.close}
              </title>
            </rect>
          </g>
        );
      })}
      {candles.map((c, i) =>
        i % 4 === 0 ? (
          <text
            key={`x${c.label}`}
            x={cx(i)}
            y={height - 8}
            textAnchor="middle"
            className="fill-faint text-[9px]"
          >
            {c.label}
          </text>
        ) : null,
      )}
    </svg>
  );
}
