import { useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, Eye, TrendingUp } from "lucide-react";
import { api, useApi } from "../../lib/api";
import type { CompanyBriefing } from "../../types";

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

const COLLAPSED_COUNT = 4;

export default function MondayBriefing({
  onSelect,
}: {
  onSelect: (id: string) => void;
}) {
  const briefing = useApi(api.briefing, []);
  const [expanded, setExpanded] = useState(false);

  const companies = useMemo(
    () =>
      [...(briefing.data?.companies ?? [])].sort(
        (a, b) => SENTIMENT_RANK[a.sentiment] - SENTIMENT_RANK[b.sentiment],
      ),
    [briefing.data],
  );
  const visible = expanded ? companies : companies.slice(0, COLLAPSED_COUNT);

  return (
    <section className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-txt">Monday briefing</h3>
          <p className="text-[11px] text-faint">
            What changed over the week and what it could mean — one read per covered company.
          </p>
        </div>
        {briefing.data?.date && (
          <span className="text-[10px] uppercase tracking-wide text-faint">
            Generated {briefing.data.date} · Asia/Singapore
          </span>
        )}
      </div>

      {briefing.loading && (
        <p className="mt-3 text-[12px] text-faint">Synthesizing this week's briefing…</p>
      )}
      {briefing.error && (
        <p className="mt-3 text-[12px] text-neg">Couldn't load the briefing. {briefing.error}</p>
      )}
      {!briefing.loading && !briefing.error && companies.length === 0 && (
        <p className="mt-3 text-[12px] text-faint">No briefing available yet.</p>
      )}

      {companies.length > 0 && (
        <div className="mt-3 space-y-2">
          {visible.map((c) => (
            <BriefingCard key={c.id} briefing={c} onSelect={() => onSelect(c.id)} />
          ))}
        </div>
      )}

      {companies.length > COLLAPSED_COUNT && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-hairline py-1.5 text-[11px] font-medium text-muted transition hover:bg-raised"
        >
          {expanded ? "Show fewer" : `Show all ${companies.length} companies`}
          <ChevronDown size={12} className={`transition ${expanded ? "rotate-180" : ""}`} />
        </button>
      )}
    </section>
  );
}

function BriefingCard({
  briefing,
  onSelect,
}: {
  briefing: CompanyBriefing;
  onSelect: () => void;
}) {
  const style = SENTIMENT_STYLE[briefing.sentiment];
  return (
    <button
      onClick={onSelect}
      className="block w-full rounded-lg border border-hairline bg-canvas/40 px-3.5 py-3 text-left transition hover:border-pos/30 hover:bg-raised/50"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-semibold leading-snug text-txt">{briefing.headline}</p>
        <span
          className="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
          style={{ color: style.color, backgroundColor: `${style.color}1a` }}
        >
          {style.label}
        </span>
      </div>
      <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{briefing.summary}</p>

      {(briefing.potentialEffects.length > 0 || briefing.watchItems.length > 0) && (
        <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
          {briefing.potentialEffects.length > 0 && (
            <div>
              <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
                <TrendingUp size={11} /> Potential effects
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
            <div>
              <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
                <Eye size={11} /> Watch for
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
        </div>
      )}

      {briefing.sentiment === "negative" && (
        <p className="mt-2 flex items-center gap-1 text-[10px] text-neg">
          <AlertTriangle size={11} /> Flagged for attention this week
        </p>
      )}
    </button>
  );
}
