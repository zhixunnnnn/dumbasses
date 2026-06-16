// Insight panels for the dashboard — all driven by the real engine data
// (CompanyRow from /api/companies and NewsData from /api/news).
import { useMemo } from "react";
import { ExternalLink } from "lucide-react";
import type { CompanyRow, NewsData, QuadrantKey } from "../../types";
import { QUADRANT, na } from "../../lib/ui";

// ---- stat cards ------------------------------------------------------------
export function StatRow({ rows, news }: { rows: CompanyRow[]; news: NewsData | null }) {
  const scores = rows.map((r) => r.evidence_total).filter((v): v is number => v != null);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const improvers = rows.filter((r) => r.is_underpriced_improver).length;
  const hidden = rows.filter((r) => r.quadrant === "HIDDEN_WINNERS").length;
  const ids = new Set(rows.map((r) => r.id));
  const controversies = (news?.companies ?? [])
    .filter((c) => ids.has(c.company_id))
    .reduce((sum, c) => sum + (c.controversy || 0), 0);

  const cards: { label: string; value: string; accent?: string }[] = [
    { label: "SG companies screened", value: `${rows.length}` },
    { label: "Avg evidence score", value: na(avg) },
    { label: "Underpriced Improvers", value: `${improvers}`, accent: "#3ecf8e" },
    { label: "Hidden Winners", value: `${hidden}`, accent: "#3ecf8e" },
    { label: "Controversy flags", value: `${controversies}`, accent: controversies ? "#ec6a5e" : undefined },
  ];
  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-hairline bg-surface px-4 py-3 shadow-panel">
          <p className="font-mono text-xl font-semibold tabular-nums" style={{ color: c.accent }}>
            {c.value}
          </p>
          <p className="mt-0.5 text-[11px] leading-snug text-faint">{c.label}</p>
        </div>
      ))}
    </section>
  );
}

// ---- sector leaderboard ----------------------------------------------------
export function SectorLeaderboard({ rows }: { rows: CompanyRow[] }) {
  const sectors = useMemo(() => {
    const by = new Map<string, number[]>();
    for (const r of rows) {
      if (r.evidence_total == null) continue;
      (by.get(r.sector) ?? by.set(r.sector, []).get(r.sector)!).push(r.evidence_total);
    }
    return [...by.entries()]
      .map(([sector, vals]) => ({ sector, avg: vals.reduce((a, b) => a + b, 0) / vals.length, n: vals.length }))
      .sort((a, b) => b.avg - a.avg);
  }, [rows]);

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <h3 className="text-sm font-semibold text-txt">Sector leaderboard</h3>
      <p className="mb-3 text-[11px] text-faint">Average evidence score by sector</p>
      <div className="space-y-2">
        {sectors.map((s) => (
          <div key={s.sector} className="flex items-center gap-3">
            <span className="w-28 shrink-0 truncate text-[12px] text-muted" title={s.sector}>
              {s.sector}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
              <div className="h-full rounded-full bg-pos/70" style={{ width: `${Math.max(3, s.avg)}%` }} />
            </div>
            <span className="w-9 shrink-0 text-right font-mono text-[12px] tabular-nums text-txt">
              {s.avg.toFixed(0)}
            </span>
          </div>
        ))}
        {sectors.length === 0 && <p className="text-[12px] text-faint">No companies in view.</p>}
      </div>
    </div>
  );
}

// ---- evidence-score distribution -------------------------------------------
const BINS = [
  { lo: 0, hi: 40, label: "0–40" },
  { lo: 40, hi: 55, label: "40–55" },
  { lo: 55, hi: 70, label: "55–70" },
  { lo: 70, hi: 85, label: "70–85" },
  { lo: 85, hi: 101, label: "85–100" },
];
export function ScoreHistogram({ rows }: { rows: CompanyRow[] }) {
  const counts = BINS.map((b) => rows.filter((r) => r.evidence_total != null && r.evidence_total >= b.lo && r.evidence_total < b.hi).length);
  const max = Math.max(1, ...counts);
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <h3 className="text-sm font-semibold text-txt">Evidence score distribution</h3>
      <p className="mb-3 text-[11px] text-faint">Companies by verified-evidence score</p>
      <div className="flex items-end gap-2" style={{ height: 96 }}>
        {BINS.map((b, i) => (
          <div key={b.label} className="flex flex-1 flex-col items-center justify-end gap-1.5">
            <span className="font-mono text-[11px] tabular-nums text-muted">{counts[i] || ""}</span>
            <div
              className="w-full rounded-t bg-pos/60"
              style={{ height: `${(counts[i] / max) * 72}px`, minHeight: counts[i] ? 3 : 0 }}
            />
            <span className="text-[10px] text-faint">{b.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- quadrant mix ----------------------------------------------------------
const ORDER: QuadrantKey[] = ["HIDDEN_WINNERS", "FUTURE_LEADERS", "VALUE_TRAPS", "OVERRATED"];
export function QuadrantMix({ rows }: { rows: CompanyRow[] }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">Quadrant mix</p>
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {ORDER.map((key) => {
          const meta = QUADRANT[key];
          const count = rows.filter((r) => r.quadrant === key).length;
          return (
            <div key={key} className="rounded-lg border border-hairline p-3" style={{ background: `${meta.color}12` }}>
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold" style={{ color: meta.color }}>
                  {meta.label}
                </span>
                <span className="font-mono text-lg font-bold tabular-nums text-txt">{count}</span>
              </div>
              <p className="mt-1 text-[10.5px] leading-snug text-faint">{meta.blurb}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---- controversy feed (from real news) -------------------------------------
export function ControversyFeed({
  rows,
  news,
  onSelect,
}: {
  rows: CompanyRow[];
  news: NewsData | null;
  onSelect: (id: string) => void;
}) {
  const ids = new Set(rows.map((r) => r.id));
  const items = (news?.companies ?? [])
    .filter((c) => ids.has(c.company_id))
    .flatMap((c) =>
      (c.headlines ?? [])
        .filter((h) => h.label === "controversy")
        .map((h) => ({ company_id: c.company_id, name: c.name, title: h.title, url: h.url })),
    )
    .slice(0, 6);

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <h3 className="text-sm font-semibold text-txt">Controversy feed</h3>
      <p className="mb-3 text-[11px] text-faint">Recent flagged ESG headlines</p>
      {items.length === 0 ? (
        <p className="text-[12px] text-faint">No controversies flagged in view.</p>
      ) : (
        <div className="space-y-2">
          {items.map((it, i) => (
            <button
              key={i}
              onClick={() => onSelect(it.company_id)}
              className="block w-full rounded-lg border border-hairline bg-canvas/40 px-3 py-2 text-left transition hover:border-neg/40 hover:bg-raised/50"
            >
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-neg" />
                <span className="truncate text-[12px] font-medium text-txt">{it.name}</span>
                {it.url && <ExternalLink size={11} className="ml-auto shrink-0 text-faint" />}
              </div>
              <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug text-muted">{it.title}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
