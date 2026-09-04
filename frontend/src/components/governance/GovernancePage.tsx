import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  Clock3,
  Download,
  ExternalLink,
  Flag,
  LoaderCircle,
  Pin,
  RefreshCw,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { OverrideForm, OverridesPanel, inferCompanyId } from "./FactOverrides";
import { loadOverrideStats, type OverrideStats } from "../../lib/overrides";
import {
  STATUS_LABELS,
  deleteFeedback,
  downloadFeedbackExport,
  listFeedback,
  loadFeedbackStats,
  reviewFeedback,
  type FeedbackRecord,
  type FeedbackStats,
  type FeedbackStatus,
} from "../../lib/feedback";

const FILTERS: Array<{ id: FeedbackStatus | "all"; label: string }> = [
  { id: "open", label: "Open" },
  { id: "reviewing", label: "In review" },
  { id: "resolved", label: "Resolved" },
  { id: "dismissed", label: "Dismissed" },
  { id: "all", label: "All" },
];

const STATUS_TONE: Record<FeedbackStatus, string> = {
  open: "border-neg/40 bg-neg/10 text-neg",
  reviewing: "border-profit/40 bg-profit/10 text-profit",
  resolved: "border-pos/40 bg-pos/10 text-pos",
  dismissed: "border-hairline bg-raised text-muted",
};

export default function GovernancePage() {
  const [view, setView] = useState<"queue" | "overrides">("queue");
  const [filter, setFilter] = useState<FeedbackStatus | "all">("open");
  const [records, setRecords] = useState<FeedbackRecord[] | null>(null);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [overrideStats, setOverrideStats] = useState<OverrideStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [rows, summary, overrides] = await Promise.all([
        listFeedback(filter),
        loadFeedbackStats(),
        loadOverrideStats().catch(() => null),
      ]);
      setRecords(rows);
      setStats(summary);
      setOverrideStats(overrides);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the review queue.");
      setRecords([]);
    } finally {
      setRefreshing(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const applyReview = async (
    id: string,
    payload: Parameters<typeof reviewFeedback>[1],
  ) => {
    try {
      const updated = await reviewFeedback(id, payload);
      setRecords((current) =>
        (current ?? []).map((row) => (row.id === id ? updated : row)),
      );
      setStats(await loadFeedbackStats());
      // A status change can move the row out of the active filter.
      if (filter !== "all" && payload.status && payload.status !== filter) {
        setRecords((current) => (current ?? []).filter((row) => row.id !== id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the review.");
    }
  };

  const removeRecord = async (id: string) => {
    try {
      await deleteFeedback(id);
      setRecords((current) => (current ?? []).filter((row) => row.id !== id));
      setStats(await loadFeedbackStats());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the flag.");
    }
  };

  const counts = stats?.byStatus ?? {};

  return (
    <div className="mx-auto flex h-full w-full max-w-6xl flex-col px-6 py-6 sm:px-10 lg:px-12">
      <header className="pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neg/15 text-neg">
              <ShieldAlert size={18} />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-txt">Governance</h1>
              <p className="mt-0.5 max-w-2xl text-sm leading-relaxed text-muted">
                Every agent response flagged in the workspace lands here for human
                review. Confirm what went wrong, write the answer the agent should
                have given, and the pair becomes RLHF training data. When the
                mistake was a specific figure, pin the right one — the agent reads
                the corrected value on the very next question.
              </p>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => void load()}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-lg border border-hairline px-3 py-2 text-xs font-semibold text-muted transition hover:text-txt disabled:opacity-50"
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
              Refresh
            </button>
            <button
              onClick={() => void downloadFeedbackExport(false)}
              className="flex items-center gap-2 rounded-lg border border-pos/35 bg-pos/10 px-3 py-2 text-xs font-semibold text-pos transition hover:bg-pos/15"
              title="Download resolved flags as RLHF preference pairs (JSONL)"
            >
              <Download size={13} />
              Export pairs
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Flags raised" value={stats?.total ?? 0} />
          <StatTile label="Awaiting review" value={counts.open ?? 0} tone="neg" />
          <StatTile
            label="Training pairs ready"
            value={stats?.trainablePairs ?? 0}
            tone="pos"
            hint="Resolved flags that carry a human-written correction"
          />
          <StatTile
            label="Values pinned"
            value={overrideStats?.active ?? 0}
            tone="pos"
            hint="Live fact overrides the agent reads instead of the engine's own output"
          />
        </div>

        <GovernanceOverview stats={stats} />
      </header>

      <div className="flex gap-2 pb-3">
        {(
          [
            { id: "queue", label: "Review queue" },
            { id: "overrides", label: "Fact overrides" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setView(tab.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              view === tab.id
                ? "bg-raised text-txt"
                : "text-muted hover:text-txt"
            }`}
          >
            {tab.label}
            {tab.id === "overrides" && overrideStats?.active ? (
              <span className="ml-1.5 text-faint">{overrideStats.active}</span>
            ) : null}
          </button>
        ))}
      </div>

      {view === "overrides" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <OverridesPanel
            onChanged={() => void loadOverrideStats().then(setOverrideStats)}
          />
        </div>
      ) : (
        <>
      <div className="flex flex-wrap gap-2 border-b border-hairline pb-4">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            onClick={() => setFilter(item.id)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              filter === item.id
                ? "border-pos bg-pos/10 text-pos"
                : "border-hairline bg-canvas/45 text-muted hover:text-txt"
            }`}
          >
            {item.label}
            {item.id !== "all" && counts[item.id] ? (
              <span className="ml-1.5 text-faint">{counts[item.id]}</span>
            ) : null}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto py-4">
        {records === null ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted">
            <LoaderCircle size={16} className="animate-spin" /> Loading review queue
          </div>
        ) : records.length === 0 ? (
          <div className="rounded-xl border border-dashed border-hairline p-8 text-center">
            <Flag size={20} className="mx-auto text-faint" />
            <p className="mt-3 text-sm font-medium text-txt">
              Nothing {filter === "all" ? "flagged" : STATUS_LABELS[filter].toLowerCase()} right now
            </p>
            <p className="mt-1 text-xs text-muted">
              Use the flag button under any agent response to send it here.
            </p>
          </div>
        ) : (
          records.map((record) => (
            <ReviewCard
              key={record.id}
              record={record}
              onReview={applyReview}
              onDelete={removeRecord}
              onPinned={() => void loadOverrideStats().then(setOverrideStats)}
            />
          ))
        )}
      </div>
        </>
      )}
    </div>
  );
}

function GovernanceOverview({ stats }: { stats: FeedbackStats | null }) {
  const total = stats?.total ?? 0;
  const resolved = stats?.byStatus.resolved ?? 0;
  const active =
    (stats?.byStatus.open ?? 0) + (stats?.byStatus.reviewing ?? 0);
  const resolutionRate = total > 0 ? Math.round((resolved / total) * 100) : 0;
  const correctionCoverage =
    resolved > 0
      ? Math.min(
          100,
          Math.round(((stats?.trainablePairs ?? 0) / resolved) * 100),
        )
      : 0;
  const issueMix = Object.entries(stats?.byReason ?? {})
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);
  const largestIssue = Math.max(1, ...issueMix.map(([, count]) => count));

  return (
    <div className="mt-3 grid gap-2.5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="rounded-xl border border-hairline bg-surface p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-1.5 text-xs font-semibold text-txt">
              <Activity size={14} className="text-pos" /> Review health
            </p>
            <p className="mt-1 text-[11px] text-muted">
              Current control-loop throughput and correction coverage.
            </p>
          </div>
          <span className="rounded-full border border-hairline bg-canvas/50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-faint">
            Live queue
          </span>
        </div>

        <div className="mt-4 space-y-3">
          <ProgressMetric
            label="Resolution rate"
            value={resolutionRate}
            detail={`${resolved} of ${total} flags`}
          />
          <ProgressMetric
            label="Correction coverage"
            value={correctionCoverage}
            detail={`${stats?.trainablePairs ?? 0} training pairs`}
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-3 text-[11px] text-muted">
          <span className="flex items-center gap-1.5">
            <Clock3 size={12} className="text-profit" /> {active} active reviews
          </span>
          <span>
            Latest flag: {stats?.latestAt ? formatWhen(stats.latestAt) : "None yet"}
          </span>
        </div>
      </section>

      <section className="rounded-xl border border-hairline bg-surface p-4">
        <div>
          <p className="text-xs font-semibold text-txt">Issue mix</p>
          <p className="mt-1 text-[11px] text-muted">
            Flag reasons ranked by frequency across the review history.
          </p>
        </div>

        {issueMix.length === 0 ? (
          <div className="mt-4 rounded-lg border border-dashed border-hairline px-3 py-5 text-center text-xs text-muted">
            Issue distribution will appear after the first response is flagged.
          </div>
        ) : (
          <div className="mt-4 space-y-2.5">
            {issueMix.map(([reason, count]) => (
              <div key={reason} className="grid grid-cols-[minmax(110px,0.8fr)_minmax(120px,1fr)_2rem] items-center gap-2">
                <span className="truncate text-[11px] text-muted">
                  {stats?.reasonLabels[reason] ?? reason}
                </span>
                <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                  <div
                    className="h-full rounded-full bg-profit"
                    style={{ width: `${Math.max(6, (count / largestIssue) * 100)}%` }}
                  />
                </div>
                <span className="text-right font-mono text-[11px] tabular-nums text-txt">
                  {count}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hairline pt-3 text-[10px] font-semibold uppercase tracking-wider text-faint">
          <span>Detect</span>
          <ArrowRight size={11} />
          <span>Review</span>
          <ArrowRight size={11} />
          <span>Correct and pin</span>
          <ArrowRight size={11} />
          <span>Export</span>
        </div>
      </section>
    </div>
  );
}

function ProgressMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]">
        <span className="text-muted">{label}</span>
        <span className="font-mono tabular-nums text-txt">
          {value}% <span className="text-faint">· {detail}</span>
        </span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-raised"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
      >
        <div
          className="h-full rounded-full bg-pos"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number;
  tone?: "pos" | "neg";
  hint?: string;
}) {
  const color =
    tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-txt";
  return (
    <div className="rounded-xl border border-hairline bg-surface p-3.5" title={hint}>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function ReviewCard({
  record,
  onReview,
  onDelete,
  onPinned,
}: {
  record: FeedbackRecord;
  onReview: (
    id: string,
    payload: Parameters<typeof reviewFeedback>[1],
  ) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onPinned: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState(record.reviewerNote);
  const [correction, setCorrection] = useState(record.correctedResponse);
  const [pinning, setPinning] = useState(false);
  const [saving, setSaving] = useState(false);

  const dirty =
    note !== record.reviewerNote || correction !== record.correctedResponse;

  const sources = useMemo(
    () => record.artifacts?.sources ?? [],
    [record.artifacts],
  );

  const save = async (status?: FeedbackStatus) => {
    setSaving(true);
    await onReview(record.id, {
      status,
      reviewerNote: note,
      correctedResponse: correction,
    });
    setSaving(false);
  };

  return (
    <article className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_TONE[record.status]}`}
        >
          {STATUS_LABELS[record.status]}
        </span>
        <span className="rounded-full border border-hairline bg-canvas/50 px-2.5 py-0.5 text-[11px] text-muted">
          {record.reasonLabel}
        </span>
        {record.model && (
          <span className="text-[11px] text-faint">{record.model}</span>
        )}
        <span className="ml-auto text-[11px] text-faint">
          {formatWhen(record.createdAt)}
        </span>
      </div>

      <p className="mt-3 text-[11px] font-semibold uppercase tracking-wider text-faint">
        Prompt
      </p>
      <p className="mt-1 whitespace-pre-wrap text-sm text-txt">
        {record.promptText || <span className="text-faint">Not captured</span>}
      </p>

      <p className="mt-3 text-[11px] font-semibold uppercase tracking-wider text-faint">
        Flagged response
      </p>
      <p
        className={`mt-1 whitespace-pre-wrap text-sm leading-relaxed text-muted ${
          expanded ? "" : "line-clamp-6"
        }`}
      >
        {record.responseText}
      </p>
      {record.responseText.length > 400 && (
        <button
          onClick={() => setExpanded((value) => !value)}
          className="mt-1 text-[11px] font-semibold text-pos transition hover:brightness-110"
        >
          {expanded ? "Show less" : "Show full response"}
        </button>
      )}

      {record.comment && (
        <div className="mt-3 rounded-lg border border-neg/25 bg-neg/5 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-neg">
            Reporter comment
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-txt">{record.comment}</p>
        </div>
      )}

      {sources.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Sources the agent cited ({sources.length})
          </p>
          <ul className="mt-1.5 space-y-1">
            {sources.slice(0, 6).map((source) => (
              <li key={source.url}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-start gap-1.5 text-xs text-muted transition hover:text-pos"
                >
                  <ExternalLink size={11} className="mt-0.5 shrink-0" />
                  <span className="truncate">{source.title || source.url}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 grid gap-3 border-t border-hairline pt-4 md:grid-cols-2">
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Reviewer note
          </span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={4}
            placeholder="What actually went wrong, and why?"
            className="mt-1.5 w-full resize-y rounded-lg border border-hairline bg-canvas/50 px-3 py-2 text-sm text-txt outline-none placeholder:text-faint"
          />
        </label>
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Corrected response{" "}
            <span className="normal-case text-faint">
              — becomes the &ldquo;chosen&rdquo; side of the RLHF pair
            </span>
          </span>
          <textarea
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            rows={4}
            placeholder="Write the answer the agent should have given."
            className="mt-1.5 w-full resize-y rounded-lg border border-hairline bg-canvas/50 px-3 py-2 text-sm text-txt outline-none placeholder:text-faint"
          />
        </label>
      </div>

      <div className="mt-3 rounded-lg border border-hairline bg-canvas/40">
        <button
          onClick={() => setPinning((value) => !value)}
          className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-semibold text-muted transition hover:text-txt"
        >
          <Pin size={13} />
          {pinning ? "Hide" : "Got a figure wrong? Pin the correct value"}
          <span className="ml-auto font-normal text-faint">
            Applied before the agent reads it
          </span>
        </button>
        {pinning && (
          <div className="border-t border-hairline p-3">
            <OverrideForm
              defaultCompanyId={inferCompanyId(record.pageContext)}
              feedbackId={record.id}
              onSaved={onPinned}
            />
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={() => void save("resolved")}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-pos px-3 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-50"
        >
          <Check size={13} />
          Resolve
        </button>
        <button
          onClick={() => void save("reviewing")}
          disabled={saving}
          className="rounded-lg border border-hairline px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-txt disabled:opacity-50"
        >
          Mark in review
        </button>
        <button
          onClick={() => void save("dismissed")}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg border border-hairline px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-txt disabled:opacity-50"
        >
          <X size={13} />
          Dismiss
        </button>
        {dirty && (
          <button
            onClick={() => void save()}
            disabled={saving}
            className="rounded-lg border border-pos/35 bg-pos/10 px-3 py-1.5 text-xs font-semibold text-pos transition disabled:opacity-50"
          >
            Save without changing status
          </button>
        )}
        <button
          onClick={() => void onDelete(record.id)}
          className="ml-auto flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-faint transition hover:text-neg"
          title="Delete this flag permanently"
        >
          <Trash2 size={13} />
          Delete
        </button>
      </div>

      {record.reviewedAt && (
        <p className="mt-2 text-[11px] text-faint">
          Last reviewed {formatWhen(record.reviewedAt)}
        </p>
      )}
    </article>
  );
}

function formatWhen(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
