type Props = {
  data: number[];
  labels?: string[];
  color?: string;
  height?: number;
  valueSuffix?: string;
  animate?: boolean;
};

export default function LineChart({
  data,
  labels,
  color = "#4cc4d4",
  height = 170,
  valueSuffix = "",
  animate = true,
}: Props) {
  const width = 520;
  const padX = 8;
  const padY = 18;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const x = (i: number) => padX + (i / (data.length - 1)) * (width - padX * 2);
  const y = (v: number) =>
    height - padY - ((v - min) / span) * (height - padY * 2);

  const line = data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `${x(0)},${height - padY} ${line} ${x(data.length - 1)},${
    height - padY
  }`;
  const id = `line-${color.replace("#", "")}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full text-white"
      preserveAspectRatio="none"
      role="img"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.26} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((g) => (
        <line
          key={g}
          x1={padX}
          x2={width - padX}
          y1={padY + g * (height - padY * 2)}
          y2={padY + g * (height - padY * 2)}
          stroke="currentColor"
          strokeOpacity={0.07}
        />
      ))}
      <polygon points={area} fill={`url(#${id})`} />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        pathLength={animate ? 1 : undefined}
        style={
          animate
            ? {
                strokeDasharray: 1,
                strokeDashoffset: 1,
                animation: "draw-line 1.1s ease forwards",
              }
            : undefined
        }
      />
      {data.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={2.2} fill={color}>
          <title>
            {labels?.[i] ? `${labels[i]}: ` : ""}
            {v}
            {valueSuffix}
          </title>
        </circle>
      ))}
    </svg>
  );
}
