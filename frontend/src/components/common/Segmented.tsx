type Option<T extends string | number> = { value: T; label: string };

type Props<T extends string | number> = {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
};

export default function Segmented<T extends string | number>({
  options,
  value,
  onChange,
}: Props<T>) {
  return (
    <div className="inline-flex rounded-lg border border-hairline bg-canvas p-0.5">
      {options.map((opt) => (
        <button
          key={String(opt.value)}
          onClick={() => onChange(opt.value)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
            value === opt.value
              ? "bg-raised text-txt"
              : "text-muted hover:text-txt"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
