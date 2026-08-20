import { useEffect, useState } from "react";
import { CircleCheck, CircleX, LoaderCircle, Server, Zap } from "lucide-react";

type ProbeResult = {
  ok: boolean;
  url: string | null;
  detail: string;
};

type ProbeResponse = {
  searxng: ProbeResult;
  crawl4ai: ProbeResult;
};

/** Base URLs for the self-hosted Crawl4AI + SearXNG pair.
 *
 *  The values are normalized server-side (scheme added, trailing slash and any
 *  pasted endpoint path stripped), so "myhost.up.railway.app" and
 *  "https://myhost.up.railway.app/search/" both resolve to the same origin.
 *  Leave a field blank to fall back to SEARXNG_BASE_URL / CRAWL4AI_BASE_URL. */
export default function SelfHostedScrapers({
  searxngBaseUrl,
  crawl4aiBaseUrl,
  saving,
  onSave,
}: {
  searxngBaseUrl: string;
  crawl4aiBaseUrl: string;
  saving: boolean;
  onSave: (patch: {
    searxngBaseUrl?: string;
    crawl4aiBaseUrl?: string;
  }) => void;
}) {
  const [searxng, setSearxng] = useState(searxngBaseUrl);
  const [crawl4ai, setCrawl4ai] = useState(crawl4aiBaseUrl);
  const [probe, setProbe] = useState<ProbeResponse | null>(null);
  const [testing, setTesting] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  useEffect(() => setSearxng(searxngBaseUrl), [searxngBaseUrl]);
  useEffect(() => setCrawl4ai(crawl4aiBaseUrl), [crawl4aiBaseUrl]);

  const dirty = searxng !== searxngBaseUrl || crawl4ai !== crawl4aiBaseUrl;

  const runProbe = async () => {
    setTesting(true);
    setProbeError(null);
    try {
      const response = await fetch("/api/settings/scraping/test", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`Probe failed (${response.status})`);
      setProbe((await response.json()) as ProbeResponse);
    } catch (err) {
      setProbeError(
        err instanceof Error ? err.message : "Could not reach the endpoints.",
      );
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mt-5 border-t border-hairline pt-5">
      <div className="flex items-center gap-2">
        <Server size={15} className="text-purpose" />
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">
          Self-hosted endpoints
        </p>
      </div>
      <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted">
        SearXNG handles discovery, Crawl4AI renders and extracts pages. Paste each
        service&rsquo;s base URL — the scheme, trailing slash, and any endpoint
        path are normalized for you. Blank falls back to the deployment&rsquo;s
        SEARXNG_BASE_URL / CRAWL4AI_BASE_URL.
      </p>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <UrlField
          label="SearXNG base URL"
          placeholder="https://searxng-production.up.railway.app"
          value={searxng}
          onChange={setSearxng}
          disabled={saving}
          probe={probe?.searxng}
        />
        <UrlField
          label="Crawl4AI base URL"
          placeholder="https://crawl4ai-production.up.railway.app"
          value={crawl4ai}
          onChange={setCrawl4ai}
          disabled={saving}
          probe={probe?.crawl4ai}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={() =>
            onSave({
              searxngBaseUrl: searxng.trim(),
              crawl4aiBaseUrl: crawl4ai.trim(),
            })
          }
          disabled={!dirty || saving}
          className="rounded-lg bg-pos px-3 py-2 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-40"
        >
          {saving ? "Saving" : "Save endpoints"}
        </button>
        <button
          onClick={() => void runProbe()}
          disabled={testing}
          className="flex items-center gap-2 rounded-lg border border-hairline px-3 py-2 text-xs font-semibold text-muted transition hover:text-txt disabled:opacity-50"
        >
          {testing ? (
            <LoaderCircle size={13} className="animate-spin" />
          ) : (
            <Zap size={13} />
          )}
          Test connection
        </button>
        {dirty && (
          <span className="text-[11px] text-faint">
            Save before testing — the probe uses the stored values.
          </span>
        )}
      </div>

      {probeError && (
        <p className="mt-2 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {probeError}
        </p>
      )}
    </div>
  );
}

function UrlField({
  label,
  placeholder,
  value,
  onChange,
  disabled,
  probe,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  probe?: ProbeResult;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 w-full rounded-lg border border-hairline bg-canvas/50 px-3 py-2 font-mono text-xs text-txt outline-none placeholder:text-faint"
      />
      {probe && (
        <span
          className={`mt-1.5 flex items-start gap-1.5 text-[11px] leading-relaxed ${
            probe.ok ? "text-pos" : "text-neg"
          }`}
        >
          {probe.ok ? (
            <CircleCheck size={12} className="mt-0.5 shrink-0" />
          ) : (
            <CircleX size={12} className="mt-0.5 shrink-0" />
          )}
          <span className="min-w-0">{probe.detail}</span>
        </span>
      )}
    </label>
  );
}
