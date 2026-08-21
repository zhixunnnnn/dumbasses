import { useCallback, useEffect, useState } from "react";
import { Check, LoaderCircle, RotateCcw, Stamp } from "lucide-react";

type RaterKey = "msci" | "sustainalytics" | "sp" | "cdp";

type ManualRating = {
  company_id: string;
  rater: RaterKey;
  value_raw: string;
  assessment_year?: number | null;
  observed_on: string;
  source_url: string;
  note?: string | null;
  updated_at: string;
};

type RatersResponse = { raters: ManualRating[] };
type Company = { id: string; name: string; ticker: string };

const RATER_ORDER: RaterKey[] = ["msci", "sustainalytics", "sp", "cdp"];

const RATER_LABEL: Record<RaterKey, string> = {
  msci: "MSCI",
  sustainalytics: "Sustainalytics",
  sp: "S&P Global",
  cdp: "CDP",
};

// Each rater's own scale, spelled out so nobody types a percentile in by mistake.
const RATER_SCALE: Record<RaterKey, string> = {
  msci: "CCC · B · BB · BBB · A · AA · AAA",
  sustainalytics: "ESG Risk Rating 0–100 (lower = better)",
  sp: "ESG Score 0–100 (higher = better)",
  cdp: "D- · D · C- · C · B- · B · A- · A",
};

function keyOf(companyId: string, rater: RaterKey) {
  return `${companyId}::${rater}`;
}

export default function RatersPanel() {
  const [ratings, setRatings] = useState<ManualRating[] | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [draftObserved, setDraftObserved] = useState("");
  const [draftUrl, setDraftUrl] = useState("");
  const [draftYear, setDraftYear] = useState("");

  const load = useCallback(async () => {
    const [ratersRes, companiesRes] = await Promise.all([
      fetch("/api/settings/raters"),
      fetch("/api/companies"),
    ]);
    if (!ratersRes.ok) throw new Error(`Rater request failed (${ratersRes.status})`);
    const payload = (await ratersRes.json()) as RatersResponse;
    const rows = companiesRes.ok ? ((await companiesRes.json()) as Company[]) : [];
    return { ratings: payload.raters ?? [], companies: rows };
  }, []);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((result) => {
        if (cancelled) return;
        setRatings(result.ratings);
        setCompanies(result.companies);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load rater ratings.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const stored = (companyId: string, rater: RaterKey) =>
    (ratings ?? []).find((row) => row.company_id === companyId && row.rater === rater) ?? null;

  const startEdit = (companyId: string, rater: RaterKey) => {
    const row = stored(companyId, rater);
    setEditing(keyOf(companyId, rater));
    setDraftValue(row?.value_raw ?? "");
    setDraftObserved(row?.observed_on ?? new Date().toISOString().slice(0, 10));
    setDraftUrl(row?.source_url ?? "");
    setDraftYear(row?.assessment_year ? String(row.assessment_year) : "");
    setError(null);
  };

  const save = async (companyId: string, rater: RaterKey) => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/raters", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companyId,
          rater,
          valueRaw: draftValue.trim(),
          observedOn: draftObserved.trim(),
          sourceUrl: draftUrl.trim(),
          assessmentYear: draftYear.trim() ? Number(draftYear.trim()) : null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Rating update failed (${response.status})`);
      }
      const payload = (await response.json()) as RatersResponse;
      setRatings(payload.raters ?? []);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the rating.");
    } finally {
      setSaving(false);
    }
  };

  const revert = async (companyId: string, rater: RaterKey) => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/settings/raters/${encodeURIComponent(companyId)}/${encodeURIComponent(rater)}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Could not revert ${companyId} ${rater}.`);
      }
      const payload = (await response.json()) as RatersResponse;
      setRatings(payload.raters ?? []);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revert the rating.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mt-5 rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pos/15 text-pos">
          <Stamp size={18} />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Rater provenance
          </p>
          <h2 className="mt-1 text-xl font-semibold text-txt">Rater ratings</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
            S&amp;P Global and Sustainalytics publish current ratings on free public pages
            but forbid bulk scraping, so those are read by a person and entered here. An
            entry counts as a REAL rating: consensus and the Trust Meter stay N.A. until a
            company has two of them. The source link and the date you read it are required
            — a rating without provenance is not a rating. Each entry lands on the rating
            year you record (blank = the latest analysis year) and is never spread across
            other years.
          </p>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {!ratings ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" /> Loading rater ratings
        </div>
      ) : companies.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-hairline p-4 text-sm text-muted">
          No companies are loaded yet.
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {companies.map((company) => (
            <div key={company.id} className="rounded-xl border border-hairline bg-canvas/40 p-4">
              <p className="text-sm font-semibold text-txt">
                {company.name}{" "}
                <span className="font-mono text-[11px] text-faint">{company.ticker}</span>
              </p>
              <table className="mt-3 w-full table-fixed">
                <tbody className="divide-y divide-hairline">
                  {RATER_ORDER.map((rater) => {
                    const row = stored(company.id, rater);
                    const rowKey = keyOf(company.id, rater);
                    const isEditing = editing === rowKey;
                    return (
                      <tr key={rowKey} className="align-middle">
                        <td className="w-32 py-2 text-xs text-muted">{RATER_LABEL[rater]}</td>
                        <td className="w-24 py-2 font-mono text-sm tabular-nums text-txt">
                          {row ? row.value_raw : "N.A."}
                        </td>
                        <td className="py-2">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                              row
                                ? "border-pos/40 bg-pos/10 text-pos"
                                : "border-hairline bg-raised text-muted"
                            }`}
                          >
                            {row ? "real · hand-entered" : "illustrative"}
                          </span>
                          {row && (
                            <>
                              <span className="ml-2 text-[10px] text-faint">
                                {row.assessment_year ? `${row.assessment_year} rating · ` : ""}
                                read {row.observed_on}
                              </span>
                              <a
                                href={row.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="ml-2 text-[10px] text-pos hover:underline"
                              >
                                source
                              </a>
                            </>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          {isEditing ? (
                            <span className="flex flex-wrap items-center justify-end gap-1.5">
                              <input
                                value={draftValue}
                                onChange={(event) => setDraftValue(event.target.value)}
                                placeholder={RATER_SCALE[rater]}
                                title={RATER_SCALE[rater]}
                                disabled={saving}
                                className="w-32 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt placeholder:text-faint"
                              />
                              <input
                                type="number"
                                value={draftYear}
                                onChange={(event) => setDraftYear(event.target.value)}
                                placeholder="rating year"
                                title="The year the rating is FOR, as the rater states it (blank = latest analysis year)"
                                disabled={saving}
                                className="w-28 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt placeholder:text-faint"
                              />
                              <input
                                type="date"
                                value={draftObserved}
                                onChange={(event) => setDraftObserved(event.target.value)}
                                disabled={saving}
                                title="The date you read this value on the rater's page"
                                className="w-36 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt"
                              />
                              <input
                                value={draftUrl}
                                onChange={(event) => setDraftUrl(event.target.value)}
                                placeholder="https://… source page"
                                disabled={saving}
                                className="w-56 rounded-lg border border-hairline bg-surface px-2 py-1.5 text-xs text-txt placeholder:text-faint"
                              />
                              <button
                                onClick={() => void save(company.id, rater)}
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
                                onClick={() => startEdit(company.id, rater)}
                                className="rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-muted transition hover:text-txt"
                              >
                                {row ? "Edit" : "Enter"}
                              </button>
                              {row && (
                                <button
                                  onClick={() => void revert(company.id, rater)}
                                  disabled={saving}
                                  title="Remove the hand-entered value"
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
