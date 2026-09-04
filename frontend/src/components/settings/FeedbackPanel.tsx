import { useEffect, useState } from "react";
import { Download, Flag, LoaderCircle, ShieldAlert } from "lucide-react";
import {
  STATUS_LABELS,
  downloadFeedbackExport,
  listFeedback,
  loadFeedbackStats,
  type FeedbackRecord,
  type FeedbackStats,
} from "../../lib/feedback";
import { useNavigation } from "../../navigation/NavigationContext";

/** Read-only RLHF summary. Reviewing and correcting happens on the Governance
 *  page — this panel exists so the flagged-response pipeline is discoverable from
 *  Settings and the training export is one click away. */
export default function FeedbackPanel() {
  const { navigate } = useNavigation();
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [recent, setRecent] = useState<FeedbackRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadFeedbackStats(), listFeedback("all")])
      .then(([summary, rows]) => {
        if (cancelled) return;
        setStats(summary);
        setRecent(rows.slice(0, 5));
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load flagged responses.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const reasonRows = Object.entries(stats?.byReason ?? {}).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <section className="mt-5 rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neg/15 text-neg">
            <Flag size={18} />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">
              Human feedback
            </p>
            <h2 className="mt-1 text-xl font-semibold text-txt">
              Flagged agent responses
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
              Responses flagged in the assistant collect here. Once a reviewer
              writes the corrected answer in Governance, the flag becomes a
              preference pair — the flagged answer is the rejected side, the
              correction is the chosen side — exportable as JSONL for RLHF.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2">
          <button
            onClick={() => navigate({ name: "governance" })}
            className="flex items-center justify-center gap-2 rounded-lg bg-pos px-3 py-2 text-xs font-semibold text-canvas transition hover:brightness-105"
          >
            <ShieldAlert size={14} />
            Open Governance
          </button>
          <button
            onClick={() => void downloadFeedbackExport(false)}
            className="flex items-center justify-center gap-2 rounded-lg border border-hairline px-3 py-2 text-xs font-semibold text-muted transition hover:text-txt"
          >
            <Download size={14} />
            Export JSONL
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {!stats ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" /> Loading feedback
        </div>
      ) : stats.total === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-hairline p-5 text-sm text-muted">
          No responses have been flagged yet. The flag button sits under every
          agent reply in the assistant and the floating copilot.
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Total flags" value={stats.total} />
            <Tile label="Awaiting review" value={stats.byStatus.open ?? 0} tone="neg" />
            <Tile label="Resolved" value={stats.byStatus.resolved ?? 0} tone="pos" />
            <Tile
              label="Training pairs"
              value={stats.trainablePairs}
              tone="pos"
            />
          </div>

          {reasonRows.length > 0 && (
            <div className="mt-5 border-t border-hairline pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
                Why responses were flagged
              </p>
              <div className="mt-2 space-y-1.5">
                {reasonRows.map(([reason, count]) => (
                  <div key={reason} className="flex items-center gap-3">
                    <span className="w-56 shrink-0 truncate text-xs text-muted">
                      {stats.reasonLabels[reason] ?? reason}
                    </span>
                    <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-raised">
                      <div
                        className="h-full rounded-full bg-neg"
                        style={{
                          width: `${Math.max(4, (count / stats.total) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-txt">
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5 border-t border-hairline pt-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
              Most recent
            </p>
            <div className="mt-2 space-y-1.5">
              {recent.map((record) => (
                <button
                  key={record.id}
                  onClick={() => navigate({ name: "governance" })}
                  className="flex w-full items-center gap-3 rounded-lg border border-hairline bg-canvas/40 px-3 py-2 text-left transition hover:bg-raised"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-txt">
                      {record.promptText || record.responseText.slice(0, 90)}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-faint">
                      {record.reasonLabel}
                      {record.comment ? ` — ${record.comment}` : ""}
                    </span>
                  </span>
                  {record.surface === "sample" && (
                    <span className="shrink-0 rounded-full border border-profit/30 bg-profit/10 px-2 py-0.5 text-[10px] font-semibold text-profit">
                      Sample
                    </span>
                  )}
                  <span className="shrink-0 rounded-full border border-hairline bg-raised px-2 py-0.5 text-[10px] font-semibold text-muted">
                    {STATUS_LABELS[record.status]}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "pos" | "neg";
}) {
  const color =
    tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-txt";
  return (
    <div className="rounded-xl border border-hairline bg-canvas/45 p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>
        {value}
      </p>
    </div>
  );
}
