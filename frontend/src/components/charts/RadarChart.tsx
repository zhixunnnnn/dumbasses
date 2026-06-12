import type { Metric } from "../../types";

type Props = {
  data: Metric[];
  color?: string;
  size?: number;
};

export default function RadarChart({
  data,
  color = "#4cc4d4",
  size = 220,
}: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 30;
  const n = data.length;

  const at = (value: number, i: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const radius = (value / 100) * r;
    return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
  };

  const shape = data.map((d, i) => at(d.value, i).join(",")).join(" ");

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full text-white" role="img">
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={data
            .map((_, i) => {
              const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
              return `${cx + r * ring * Math.cos(angle)},${
                cy + r * ring * Math.sin(angle)
              }`;
            })
            .join(" ")}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.08}
        />
      ))}
      {data.map((_, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={cx + r * Math.cos(angle)}
            y2={cy + r * Math.sin(angle)}
            stroke="currentColor"
            strokeOpacity={0.08}
          />
        );
      })}
      <polygon
        points={shape}
        fill={color}
        fillOpacity={0.2}
        stroke={color}
        strokeWidth={2}
      />
      {data.map((d, i) => {
        const [px, py] = at(d.value, i);
        return <circle key={i} cx={px} cy={py} r={2.6} fill={color} />;
      })}
      {data.map((d, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        return (
          <text
            key={`l${i}`}
            x={cx + (r + 16) * Math.cos(angle)}
            y={cy + (r + 16) * Math.sin(angle)}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-muted text-[10px]"
          >
            {d.label}
          </text>
        );
      })}
    </svg>
  );
}
