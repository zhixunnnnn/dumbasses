import { AlertTriangle } from "lucide-react";
import type { Company } from "../../types";
import { recentControversies } from "../../data/selectors";

const SEVERITY_COLOR = {
  high: "#ec6a5e",
  medium: "#e0b24a",
  low: "#9a968e",
} as const;

export default function ControversyFeed({
  companies,
  onSelect,
}: {
  companies: Company[];
  onSelect: (company: Company) => void;
}) {
  const items = recentControversies(companies, 6);
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        Controversy radar
      </p>
      {items.length === 0 ? (
        <p className="mt-4 text-sm text-muted">No flags in current view.</p>
      ) : (
        <ul className="mt-2">
          {items.map((item, i) => (
            <li
              key={`${item.company.id}-${i}`}
              className={i > 0 ? "border-t border-hairline" : ""}
            >
              <button
                onClick={() => onSelect(item.company)}
                className="flex w-full items-start gap-3 py-3 text-left transition hover:opacity-80"
              >
                <span
                  className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    background: `${SEVERITY_COLOR[item.severity]}22`,
                    color: SEVERITY_COLOR[item.severity],
                  }}
                >
                  <AlertTriangle size={13} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-txt">{item.title}</span>
                  <span className="block text-[11px] text-faint">
                    {item.company.name} · {item.year}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
