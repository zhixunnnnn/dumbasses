import { useEffect, useMemo, useState } from "react";
import { ExternalLink, LoaderCircle, Pin, Trash2 } from "lucide-react";
import { COMPANIES } from "../../data/companies";
import {
  deleteOverride,
  listOverrides,
  loadOverrideFields,
  saveOverride,
  type OverrideField,
  type OverrideRecord,
} from "../../lib/overrides";

/** A flagged answer usually names the company it got wrong. Reuse whatever the
 *  chat published so the reviewer does not re-pick it from a dropdown. */
export function inferCompanyId(
  pageContext: Record<string, unknown> | null | undefined,
): string {
  if (!pageContext) return "";
  const direct = pageContext.companyId;
  if (typeof direct === "string" && direct) return direct;
  const company = pageContext.company;
  if (company && typeof company === "object") {
    const id = (company as { id?: unknown; company_id?: unknown }).id
      ?? (company as { company_id?: unknown }).company_id;
    if (typeof id === "string" && id) return id;
  }
  return "";
}

function useOverrideFields() {
  const [fields, setFields] = useState<OverrideField[]>([]);
  useEffect(() => {
    let cancelled = false;
    void loadOverrideFields()
      .then((rows) => {
        if (!cancelled) setFields(rows);
      })
      .catch(() => {
        if (!cancelled) setFields([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return fields;
}

export function OverrideForm({
  defaultCompanyId = "",
  feedbackId = null,
  onSaved,
}: {
  defaultCompanyId?: string;
  feedbackId?: string | null;
  onSaved?: (record: OverrideRecord) => void;
}) {
  const fields = useOverrideFields();
  const [companyId, setCompanyId] = useState(defaultCompanyId);
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    setCompanyId(defaultCompanyId);
  }, [defaultCompanyId]);

  useEffect(() => {
    if (!field && fields.length) setField(fields[0].field);
  }, [fields, field]);

  const spec = useMemo(
    () => fields.find((row) => row.field === field) ?? null,
    [fields, field],
  );

  const submit = async () => {
    setError(null);
    setSaved(null);
    if (!companyId) {
      setError("Pick the company this correction applies to.");
      return;
    }
    if (!value.trim()) {
      setError("Enter the corrected value.");
      return;
    }
    setSaving(true);
    try {
      const record = await saveOverride({
        companyId,
        field,
        value: spec?.kind === "number" ? Number(value) : value.trim(),
        note,
        sourceUrl,
        feedbackId,
        expiresAt: expiresAt || null,
      });
      setSaved(`${record.fieldLabel} pinned for ${record.companyId}.`);
      setValue("");
      setNote("");
      setSourceUrl("");
      setExpiresAt("");
      onSaved?.(record);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not pin the value.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Labelled label="Company">
          <select
            value={companyId}
            onChange={(event) => setCompanyId(event.target.value)}
            className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none"
          >
            <option value="">Select…</option>
            {COMPANIES.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name} ({company.id})
              </option>
            ))}
          </select>
        </Labelled>
        <Labelled label="Field">
          <select
            value={field}
            onChange={(event) => setField(event.target.value)}
            className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none"
          >
            {fields.map((row) => (
              <option key={row.field} value={row.field}>
                {row.label}
              </option>
            ))}
          </select>
        </Labelled>
        <Labelled
          label="Correct value"
          hint={
            spec?.kind === "number" && spec.min != null && spec.max != null
              ? `${spec.min}–${spec.max}`
              : spec?.hint || undefined
          }
        >
          <input
            type={spec?.kind === "number" ? "number" : "text"}
            step="any"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={spec?.kind === "number" ? "e.g. 71.2" : "https://…"}
            className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none placeholder:text-faint"
          />
        </Labelled>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Labelled label="Why (shown to the agent)" className="sm:col-span-2">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="e.g. Restated in the FY2023 report, p.42"
            className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none placeholder:text-faint"
          />
        </Labelled>
        <Labelled label="Expires" hint="Optional — for figures that restate">
          <input
            type="date"
            value={expiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
            className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none"
          />
        </Labelled>
      </div>

      <Labelled label="Source URL" hint="Optional">
        <input
          value={sourceUrl}
          onChange={(event) => setSourceUrl(event.target.value)}
          placeholder="https://…"
          className="w-full rounded-lg border border-hairline bg-canvas/50 px-2.5 py-2 text-sm text-txt outline-none placeholder:text-faint"
        />
      </Labelled>

      {error && (
        <p className="rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}
      {saved && (
        <p className="rounded-lg border border-pos/30 bg-pos/10 px-3 py-2 text-xs text-pos">
          {saved} The agent uses it on the next question about this company.
        </p>
      )}

      <button
        onClick={() => void submit()}
        disabled={saving}
        className="flex items-center gap-1.5 rounded-lg bg-pos px-3 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-50"
      >
        <Pin size={13} />
        {saving ? "Pinning…" : "Pin corrected value"}
      </button>
    </div>
  );
}

export function OverridesPanel({ onChanged }: { onChanged?: () => void }) {
  const [records, setRecords] = useState<OverrideRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setRecords(await listOverrides());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load overrides.");
      setRecords([]);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const remove = async (id: string) => {
    try {
      await deleteOverride(id);
      setRecords((current) => (current ?? []).filter((row) => row.id !== id));
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove it.");
    }
  };

  return (
    <div className="space-y-4 py-4">
      <section className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
        <h2 className="text-sm font-semibold text-txt">Pin a corrected value</h2>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          The value is patched into the company&rsquo;s ESG payload before the agent
          reads it, so the old number never reaches the model. Use this for
          figures; use the corrected response on a flag for wording and reasoning.
        </p>
        <div className="mt-4">
          <OverrideForm
            onSaved={() => {
              void load();
              onChanged?.();
            }}
          />
        </div>
      </section>

      {error && (
        <p className="rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {records === null ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" /> Loading overrides
        </div>
      ) : records.length === 0 ? (
        <div className="rounded-xl border border-dashed border-hairline p-8 text-center">
          <Pin size={20} className="mx-auto text-faint" />
          <p className="mt-3 text-sm font-medium text-txt">No pinned values yet</p>
          <p className="mt-1 text-xs text-muted">
            Resolve a flag that got a number wrong, then pin the right one.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {records.map((row) => (
            <li
              key={row.id}
              className={`rounded-xl border bg-surface p-3.5 ${
                row.isExpired ? "border-hairline opacity-60" : "border-pos/30"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-hairline bg-canvas/50 px-2.5 py-0.5 text-[11px] font-semibold text-txt">
                  {row.companyId}
                </span>
                <span className="text-sm text-txt">{row.fieldLabel}</span>
                <span className="font-semibold tabular-nums text-pos">
                  {String(row.value)}
                </span>
                {row.isExpired && (
                  <span className="rounded-full border border-hairline px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
                    Expired
                  </span>
                )}
                {row.feedbackId && (
                  <span
                    className="rounded-full border border-hairline px-2 py-0.5 text-[10px] text-faint"
                    title={`Created from flag ${row.feedbackId}`}
                  >
                    from a flag
                  </span>
                )}
                <button
                  onClick={() => void remove(row.id)}
                  className="ml-auto flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-faint transition hover:text-neg"
                  title="Remove this override; the engine value applies again"
                >
                  <Trash2 size={13} />
                  Remove
                </button>
              </div>
              {row.note && <p className="mt-1.5 text-xs text-muted">{row.note}</p>}
              <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-faint">
                <span>Updated {formatWhen(row.updatedAt)}</span>
                {row.expiresAt && <span>Expires {formatWhen(row.expiresAt)}</span>}
                {row.sourceUrl && (
                  <a
                    href={row.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 transition hover:text-pos"
                  >
                    <ExternalLink size={10} />
                    Source
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Labelled({
  label,
  hint,
  className = "",
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        {label}
        {hint && <span className="ml-1 normal-case text-faint">— {hint}</span>}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function formatWhen(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { dateStyle: "medium" });
}
