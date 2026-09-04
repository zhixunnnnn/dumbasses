import { useCallback, useEffect, useState } from "react";
import { Check, Gauge, LoaderCircle, RotateCcw } from "lucide-react";

type BenchmarkMetric = "total" | "E" | "S" | "G";

type Benchmark = {
  industry: string;
  metric: BenchmarkMetric;
  value: number | null;
  source: string | null;
  peers?: number | null;
  updated_at?: string | null;
  is_override: boolean;
};

type BenchmarksResponse = { benchmarks: Benchmark[] };

const METRIC_ORDER: BenchmarkMetric[] = ["total", "E", "S", "G"];

const METRIC_LABEL: Record<BenchmarkMetric, string> = {
  total: "Total",
  E: "Environment",
  S: "Social",
  G: "Governance",
};

const DEFAULT_SOURCE = "CGSI";

function keyOf(industry: string, metric: BenchmarkMetric) {
  return `${industry}::${metric}`;
}

export default function BenchmarksPanel() {
  const [benchmarks, setBenchmarks] = useState<Benchmark[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [draftSource, setDraftSource] = useState(DEFAULT_SOURCE);

  const load = useCallback(async () => {
    const response = await fetch("/api/settings/benchmarks");
    if (!response.ok) throw new Error(`Benchmarks request failed (${response.status})`);
    const payload = (await response.json()) as BenchmarksResponse;
    return payload.benchmarks ?? [];
  }, []);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((rows) => {
        if (!cancelled) setBenchmarks(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load industry benchmarks.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const startEdit = (row: Benchmark) => {
    setEditing(keyOf(row.industry, row.metric));
    setDraftValue(row.value === null ? "" : String(row.value));
    setDraftSource(row.is_override && row.source ? row.source : DEFAULT_SOURCE);
    setError(null);
  };

  const saveOverride = async (row: Benchmark) => {
    const value = Number(draftValue);
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      setError("Benchmark value must be a number between 0 and 100.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/benchmarks", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: row.industry,
          metric: row.metric,
          value,
          source: draftSource.trim() || DEFAULT_SOURCE,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Benchmark update failed (${response.status})`);
      }
      const payload = (await response.json()) as BenchmarksResponse;
      setBenchmarks(payload.benchmarks ?? []);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the benchmark.");
    } finally {
      setSaving(false);
    }
  };

  const revertOverride = async (row: Benchmark) => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/settings/benchmarks/${encodeURIComponent(row.industry)}/${encodeURIComponent(row.metric)}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Could not revert ${row.industry} ${row.metric}.`);
      }
      const payload = (await response.json()) as BenchmarksResponse;
      setBenchmarks(payload.benchmarks ?? []);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revert the benchmark.");
    } finally {
      setSaving(false);
    }
  };

  const industries = Array.from(new Set((benchmarks ?? []).map((row) => row.industry))).sort();

  return (
    <section className="mt-5 rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pos/15 text-pos">
          <Gauge size={18} />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Peer comparison
          </p>
          <h2 className="mt-1 text-xl font-semibold text-txt">Industry benchmarks</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
            Compare sector-level ESG scores across the full industry universe. Panel
            medians update with scored companies, and published overrides take priority.
          </p>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {!benchmarks ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" /> Loading industry benchmarks
        </div>
      ) : industries.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-hairline p-4 text-sm text-muted">
          No industry benchmarks have been computed yet.
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {industries.map((industry) => (
            <div key={industry} className="rounded-xl border border-hairline bg-canvas/40 p-4">
              <p className="text-sm font-semibold text-txt">{industry}</p>
              <table className="mt-3 w-full table-fixed">
                <tbody className="divide-y divide-hairline">
                  {METRIC_ORDER.map((metric) => {
                    const row =
                      (benchmarks ?? []).find(
                        (item) => item.industry === industry && item.metric === metric,
                      ) ?? {
                        industry,
                        metric,
                        value: null,
                        source: null,
                        is_override: false,
                      };
                    const rowKey = keyOf(industry, metric);
                    const isEditing = editing === rowKey;
                    return (
                      <tr key={rowKey} className="align-middle">
                        <td className="w-32 py-2 text-xs text-muted">{METRIC_LABEL[metric]}</td>
                        <td className="w-24 py-2 font-mono text-sm tabular-nums text-txt">
                          {row.value === null ? "N.A." : row.value.toFixed(1)}
                        </td>
                        <td className="py-2">
                          <span
                            title={
                              row.source === "modelled baseline"
                                ? "Stable sector baseline used until scored peers are available."
                                : row.source ?? undefined
                            }
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                              row.is_override
                                ? "border-pos/40 bg-pos/10 text-pos"
                                : "border-hairline bg-raised text-muted"
                            }`}
                          >
                            {row.source ?? "no benchmark"}
                          </span>
                          {row.is_override && row.updated_at && (
                            <span className="ml-2 text-[10px] text-faint">
                              updated {row.updated_at.slice(0, 10)}
                            </span>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          {isEditing ? (
                            <span className="flex items-center justify-end gap-1.5">
                              <input
                                type="number"
                                min={0}
                                max={100}
                                step={0.1}
                                value={draftValue}
                                onChange={(event) => setDraftValue(event.target.value)}
                                disabled={saving}
                                className="w-20 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt"
                              />
                              <input
                                value={draftSource}
                                onChange={(event) => setDraftSource(event.target.value)}
                                placeholder={DEFAULT_SOURCE}
                                disabled={saving}
                                className="w-28 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt placeholder:text-faint"
                              />
                              <button
                                onClick={() => void saveOverride(row)}
                                disabled={saving}
                                className="flex items-center gap-1 rounded-lg bg-pos px-2.5 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-40"
                              >
                                {saving ? (
                                  <LoaderCircle size={13} className="animate-spin" />
                                ) : (
                                  <Check size={13} />
                                )}
                                Save
                              </button>
                              <button
                                onClick={() => setEditing(null)}
                                className="rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-muted transition hover:text-txt"
                              >
                                Cancel
                              </button>
                            </span>
                          ) : (
                            <span className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => startEdit(row)}
                                className="rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-muted transition hover:text-txt"
                              >
                                {row.is_override ? "Edit" : "Override"}
                              </button>
                              {row.is_override && (
                                <button
                                  onClick={() => void revertOverride(row)}
                                  disabled={saving}
                                  title="Revert to the panel median"
                                  className="flex items-center gap-1 rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-muted transition hover:text-txt disabled:opacity-40"
                                >
                                  <RotateCcw size={13} /> Revert
                                </button>
                              )}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
