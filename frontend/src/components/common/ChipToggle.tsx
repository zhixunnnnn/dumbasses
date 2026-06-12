export type ChipOption<T extends string> = {
  value: T;
  label: string;
  color?: string;
};

type Props<T extends string> = {
  options: ChipOption<T>[];
  selected: T[];
  onToggle: (value: T) => void;
};

export default function ChipToggle<T extends string>({
  options,
  selected,
  onToggle,
}: Props<T>) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => {
        const active = selected.includes(opt.value);
        return (
          <button
            key={opt.value}
            onClick={() => onToggle(opt.value)}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
              active
                ? "border-transparent text-canvas"
                : "border-hairline text-muted hover:text-txt"
            }`}
            style={
              active
                ? { background: opt.color ?? "#3ecf8e" }
                : undefined
            }
          >
            {opt.color && (
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: active ? "#00000055" : opt.color }}
              />
            )}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
