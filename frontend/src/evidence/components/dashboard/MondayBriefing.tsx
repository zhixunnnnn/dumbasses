import { useMemo, useState } from "react";
import { ArrowRight, ChevronDown, Eye, TrendingUp } from "lucide-react";
import type { BriefingData, CompanyBriefing } from "../../types";

const SENTIMENT_RANK: Record<CompanyBriefing["sentiment"], number> = {
  negative: 0,
  mixed: 1,
  neutral: 2,
  positive: 3,
};

const SENTIMENT_STYLE: Record<CompanyBriefing["sentiment"], { color: string; label: string }> = {
  negative: { color: "#ec6a5e", label: "Negative" },
  mixed: { color: "#e0a63e", label: "Mixed" },
  neutral: { color: "#8a8579", label: "Neutral" },
  positive: { color: "#3ecf8e", label: "Positive" },
};

type State = { data: BriefingData | null; loading: boolean; error: string | null };

function useSorted(data: BriefingData | null) {
  return useMemo(
    () =>
      [...(data?.companies ?? [])].sort(
        (a, b) => SENTIMENT_RANK[a.sentiment] - SENTIMENT_RANK[b.sentiment],
      ),
    [data],
  );
}

/** Compact desk-level rollup — sits at the top of the main column. */
export function BriefingOverview({ state }: { state: State }) {
  const overview = state.data?.overview;
  const companies = useSorted(state.data);

  const counts = useMemo(() => {
    const by = { negative: 0, mixed: 0, neutral: 0, positive: 0 };
    for (const c of companies) by[c.sentiment] += 1;
    return by;
  }, [companies]);

  if (state.loading)
    return (
      <section className="rounded-xl border border-hairline bg-surface px-4 py-3 shadow-panel">
        <p className="text-[12px] text-faint">Synthesizing this week's briefing…</p>
      </section>
    );
  if (state.error || !overview) return null;

  return (
    <section className="rounded-xl border border-hairline bg-surface px-4 py-3.5 shadow-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-txt">Monday briefing</h3>
        <span className="text-[10px] uppercase tracking-wide text-faint">
          {state.data?.date} · Asia/Singapore
        </span>
      </div>
      <p className="mt-1.5 text-[13px] font-medium leading-snug text-txt">{overview.headline}</p>
      <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{overview.summary}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {(["negative", "mixed", "neutral", "positive"] as const)
          .filter((k) => counts[k] > 0)
          .map((k) => (
            <span key={k} className="flex items-center gap-1.5 text-[11px] text-muted">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: SENTIMENT_STYLE[k].color }}
              />
              {counts[k]} {SENTIMENT_STYLE[k].label.toLowerCase()}
            </span>
          ))}
      </div>

      {overview.watchItems.length > 0 && (
        <p className="mt-2.5 text-[11px] leading-snug text-muted">
          <span className="font-semibold uppercase tracking-wide text-faint">Watch this week · </span>
          {overview.watchItems.join(" · ")}
        </p>
      )}
    </section>
  );
}

/** Per-company breakdown — sits in the right-hand rail, one collapsed row each. */
export function BriefingFeed({
  state,
  onSelect,
}: {
  state: State;
  onSelect: (id: string) => void;
}) {
  const companies = useSorted(state.data);

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <h3 className="text-sm font-semibold text-txt">By company</h3>
      <p className="mb-3 text-[11px] text-faint">This week's read, worst news first</p>

      {state.loading && <p className="text-[12px] text-faint">Loading…</p>}
      {state.error && <p className="text-[12px] text-neg">Couldn't load the briefing.</p>}
      {!state.loading && !state.error && companies.length === 0 && (
        <p className="text-[12px] text-faint">No briefing available yet.</p>
      )}

      <div className="space-y-1.5">
        {companies.map((c) => (
          <BriefingRow key={c.id} briefing={c} onSelect={() => onSelect(c.id)} />
        ))}
      </div>
    </div>
  );
}

function BriefingRow({
  briefing,
  onSelect,
}: {
  briefing: CompanyBriefing;
  onSelect: () => void;
}) {
  const [open, setOpen] = useState(false);
  const style = SENTIMENT_STYLE[briefing.sentiment];

  return (
    <div className="rounded-lg border border-hairline bg-canvas/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-3 py-2 text-left transition hover:bg-raised/50"
        aria-expanded={open}
      >
        <span
          className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: style.color }}
        />
        <span className="min-w-0 flex-1 text-[12px] font-medium leading-snug text-txt">
          {briefing.headline}
        </span>
        <ChevronDown
          size={13}
          className={`mt-0.5 shrink-0 text-faint transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="border-t border-hairline px-3 pb-2.5 pt-2">
          <p className="text-[11px] leading-relaxed text-muted">{briefing.summary}</p>

          {briefing.potentialEffects.length > 0 && (
            <div className="mt-2">
              <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
                <TrendingUp size={10} /> Potential effects
              </p>
              <ul className="mt-1 space-y-0.5">
                {briefing.potentialEffects.map((effect, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] leading-snug text-muted">
                    <span className="text-faint">·</span>
                    {effect}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {briefing.watchItems.length > 0 && (
            <div className="mt-2">
              <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
                <Eye size={10} /> Watch for
              </p>
              <ul className="mt-1 space-y-0.5">
                {briefing.watchItems.map((item, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] leading-snug text-muted">
                    <span className="text-faint">·</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={onSelect}
            className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-pos transition hover:brightness-110"
          >
            Open company <ArrowRight size={11} />
          </button>
        </div>
      )}
    </div>
  );
}
