import { useEffect, useState } from "react";
import { Check, Cpu, LoaderCircle, TriangleAlert } from "lucide-react";

type ProviderStatus = {
  id: string;
  label: string;
  available: boolean;
  reason: string | null;
  selected: boolean;
  /** False for a provider whose adapter is still a placeholder. */
  implemented: boolean;
};

type ModelSettings = {
  provider: "openrouter" | "bedrock";
  openrouterModel: string;
  bedrockModelId: string;
  bedrockRegion: string;
  temperature: number;
  maxTokens: number;
  providerStatus: Record<string, ProviderStatus>;
  catalog: {
    openrouterModels: string[];
    bedrockModels: string[];
    bedrockRegions: string[];
  };
  updatedAt: string | null;
};

export default function ModelProviderPanel() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/settings/models")
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        return (await response.json()) as ModelSettings;
      })
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load model settings.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const save = async (patch: Partial<ModelSettings>) => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/models", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Update failed (${response.status})`);
      }
      setSettings((await response.json()) as ModelSettings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save model settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mt-5 rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-purpose/15 text-purpose">
          <Cpu size={18} />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Assistant
          </p>
          <h2 className="mt-1 text-xl font-semibold text-txt">Model provider</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
            Choose which service answers agent messages. Credentials are read from
            the deployment environment only — no key is ever sent to or shown on
            this page.
          </p>
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {!settings ? (
        <div className="mt-5 flex items-center gap-2 text-sm text-muted">
          <LoaderCircle size={16} className="animate-spin" /> Loading model settings
        </div>
      ) : (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {Object.values(settings.providerStatus).map((provider) => {
              const active = settings.provider === provider.id;
              return (
                <button
                  key={provider.id}
                  onClick={() => void save({ provider: provider.id as ModelSettings["provider"] })}
                  disabled={saving}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? "border-pos bg-pos/10"
                      : "border-hairline bg-canvas/45 hover:bg-raised"
                  }`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-txt">
                      {provider.label}
                    </span>
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-md border ${
                        active
                          ? "border-pos bg-pos text-canvas"
                          : "border-hairline text-transparent"
                      }`}
                    >
                      <Check size={13} />
                    </span>
                  </span>
                  <span className="mt-2 flex flex-wrap gap-1.5">
                    <Pill
                      tone={provider.available ? "pos" : "muted"}
                      text={provider.available ? "Credentials found" : "No credentials"}
                    />
                    <Pill
                      tone={provider.implemented ? "pos" : "profit"}
                      text={provider.implemented ? "Live" : "Placeholder"}
                    />
                  </span>
                  <span className="mt-2 block text-xs leading-relaxed text-muted">
                    {provider.reason ??
                      (provider.implemented
                        ? "Ready to serve agent messages."
                        : "Settings and credential detection are wired; the adapter itself is still a stub.")}
                  </span>
                </button>
              );
            })}
          </div>

          {settings.provider === "bedrock" && (
            <p className="mt-3 flex items-start gap-2 rounded-lg border border-profit/30 bg-profit/5 px-3 py-2 text-xs leading-relaxed text-muted">
              <TriangleAlert size={14} className="mt-0.5 shrink-0 text-profit" />
              Bedrock is selected, but its adapter is a placeholder — the assistant
              keeps answering through OpenRouter until{" "}
              <code className="font-mono text-[11px] text-txt">
                build_bedrock_chat_model
              </code>{" "}
              in <code className="font-mono text-[11px] text-txt">
                backend/engine/model_settings.py
              </code>{" "}
              is implemented. That function documents the three steps required.
            </p>
          )}

          <div className="mt-5 grid gap-4 border-t border-hairline pt-5 md:grid-cols-2">
            <Field label="OpenRouter model">
              <ComboInput
                value={settings.openrouterModel}
                options={settings.catalog.openrouterModels}
                disabled={saving}
                onCommit={(value) => void save({ openrouterModel: value })}
              />
            </Field>
            <Field label="Bedrock model id">
              <ComboInput
                value={settings.bedrockModelId}
                options={settings.catalog.bedrockModels}
                disabled={saving}
                onCommit={(value) => void save({ bedrockModelId: value })}
              />
            </Field>
            <Field label="Bedrock region">
              <select
                value={settings.bedrockRegion}
                disabled={saving}
                onChange={(event) =>
                  void save({ bedrockRegion: event.target.value })
                }
                className="w-full rounded-lg border border-hairline bg-canvas/50 px-3 py-2 text-sm text-txt outline-none"
              >
                {settings.catalog.bedrockRegions.map((region) => (
                  <option key={region} value={region}>
                    {region}
                  </option>
                ))}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Temperature">
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.05}
                  defaultValue={settings.temperature}
                  disabled={saving}
                  onBlur={(event) => {
                    const value = Number(event.target.value);
                    if (
                      Number.isFinite(value) &&
                      value !== settings.temperature
                    ) {
                      void save({ temperature: value });
                    }
                  }}
                  className="w-full rounded-lg border border-hairline bg-canvas/50 px-3 py-2 text-sm text-txt outline-none"
                />
              </Field>
              <Field label="Max tokens">
                <input
                  type="number"
                  min={256}
                  max={8192}
                  step={128}
                  defaultValue={settings.maxTokens}
                  disabled={saving}
                  onBlur={(event) => {
                    const value = Number(event.target.value);
                    if (Number.isFinite(value) && value !== settings.maxTokens) {
                      void save({ maxTokens: Math.round(value) });
                    }
                  }}
                  className="w-full rounded-lg border border-hairline bg-canvas/50 px-3 py-2 text-sm text-txt outline-none"
                />
              </Field>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </span>
      <span className="mt-1.5 block">{children}</span>
    </label>
  );
}

/** A free-text field backed by a datalist, so a curated id is one click away but
 *  any other model id can still be typed. */
function ComboInput({
  value,
  options,
  disabled,
  onCommit,
}: {
  value: string;
  options: string[];
  disabled: boolean;
  onCommit: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const listId = `models-${options[0] ?? "list"}`;
  return (
    <>
      <input
        value={draft}
        list={listId}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft.trim();
          if (next && next !== value) onCommit(next);
          else setDraft(value);
        }}
        className="w-full rounded-lg border border-hairline bg-canvas/50 px-3 py-2 font-mono text-xs text-txt outline-none"
      />
      <datalist id={listId}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </>
  );
}

function Pill({ tone, text }: { tone: "pos" | "profit" | "muted"; text: string }) {
  const classes =
    tone === "pos"
      ? "border-pos/40 bg-pos/10 text-pos"
      : tone === "profit"
        ? "border-profit/40 bg-profit/10 text-profit"
        : "border-hairline bg-raised text-muted";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${classes}`}
    >
      {text}
    </span>
  );
}
