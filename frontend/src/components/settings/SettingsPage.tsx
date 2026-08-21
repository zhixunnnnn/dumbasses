import { useEffect, useState } from "react";
import {
  Check,
  Database,
  Globe,
  LoaderCircle,
  Moon,
  Palette,
  Play,
  Power,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { useThemeMode } from "../../theme/ThemeContext";
import ModelProviderPanel from "./ModelProviderPanel";
import FeedbackPanel from "./FeedbackPanel";
import SelfHostedScrapers from "./SelfHostedScrapers";

const OPTIONS = [
  {
    mode: "dark" as const,
    title: "Graphite dark",
    description: "Current dashboard look with deep panels and high-contrast cards.",
    icon: <Moon size={17} />,
  },
  {
    mode: "light" as const,
    title: "Marble light",
    description: "Warm off-white canvas with stone panels and softer borders.",
    icon: <Sun size={17} />,
  },
];

type ProviderStatus = {
  id: string;
  label: string;
  available: boolean;
  enabled: boolean;
  reason?: string | null;
  endpoints?: { searxng: string; crawl4ai: string };
};

type ScrapeSettings = {
  providers: Record<string, boolean>;
  sourceTypes: {
    verified: boolean;
    nonVerified: boolean;
    community: boolean;
  };
  providerStatus: Record<string, ProviderStatus>;
  frequency: "daily" | "weekly" | "monthly";
  maxCompanies: number;
  timezone: string;
  runAt: string;
  retainRawDays: number;
  searxngBaseUrl: string;
  crawl4aiBaseUrl: string;
  adaptiveCrawl: boolean;
  communitySentimentWeight: number;
  updatedAt?: string | null;
};

type SourceCandidate = {
  domain: string;
  status: "pending" | "approved" | "rejected";
  overlap_score: number;
  matching_claims: number;
  matched_verified_domains: string[];
  last_seen: string;
};

type SourceRegistryResponse = {
  sources: Array<{
    domain: string;
    source_class: string;
    reason?: string | null;
    is_builtin?: number;
  }>;
  candidates: SourceCandidate[];
  observed: Array<{ domain: string; pages: number; last_fetched: string }>;
};

type ResearchStatus = {
  status: string;
  running?: boolean;
  started_at?: string;
  finished_at?: string | null;
  source_count?: number;
  claim_count?: number;
  error_count?: number;
  message?: string | null;
};

const TABS = [
  { id: "appearance", label: "Appearance" },
  { id: "research", label: "Research pipeline" },
  { id: "sources", label: "Sources" },
  { id: "models", label: "Models" },
  { id: "feedback", label: "Feedback" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const FREQUENCIES = ["daily", "weekly", "monthly"] as const;
const COMPANY_COUNTS = [5, 10, 25, 50] as const;

export default function SettingsPage() {
  const { mode, setMode } = useThemeMode();
  const [tab, setTab] = useState<TabId>("appearance");
  const [scraping, setScraping] = useState<ScrapeSettings | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [sourceRegistry, setSourceRegistry] = useState<SourceRegistryResponse | null>(null);
  const [researchStatus, setResearchStatus] = useState<ResearchStatus | null>(null);
  const [startingResearch, setStartingResearch] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/settings/scraping")
      .then(async (response) => {
        if (!response.ok) throw new Error(`Settings request failed (${response.status})`);
        return (await response.json()) as ScrapeSettings;
      })
      .then((data) => {
        if (!cancelled) setScraping(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setScrapeError(error instanceof Error ? error.message : "Could not load scraping settings.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [sourcesResponse, statusResponse] = await Promise.all([
          fetch("/api/research/sources"),
          fetch("/api/research/status"),
        ]);
        if (!sourcesResponse.ok || !statusResponse.ok) return;
        const [sources, status] = await Promise.all([
          sourcesResponse.json() as Promise<SourceRegistryResponse>,
          statusResponse.json() as Promise<ResearchStatus>,
        ]);
        if (!cancelled) {
          setSourceRegistry(sources);
          setResearchStatus(status);
          if (!status.running) setStartingResearch(false);
        }
      } catch {
        // Provider settings remain usable if research status is temporarily unavailable.
      }
    };
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const saveScraping = async (next: ScrapeSettings) => {
    setSaving(true);
    setScrapeError(null);
    try {
      const response = await fetch("/api/settings/scraping", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          providers: next.providers,
          sourceTypes: next.sourceTypes,
          frequency: next.frequency,
          maxCompanies: next.maxCompanies,
          timezone: next.timezone,
          runAt: next.runAt,
          retainRawDays: next.retainRawDays,
          searxngBaseUrl: next.searxngBaseUrl,
          crawl4aiBaseUrl: next.crawl4aiBaseUrl,
        }),
      });
      if (!response.ok) throw new Error(`Settings update failed (${response.status})`);
      setScraping((await response.json()) as ScrapeSettings);
    } catch (error) {
      setScrapeError(error instanceof Error ? error.message : "Could not save scraping settings.");
    } finally {
      setSaving(false);
    }
  };

  const toggleSourceType = (key: keyof ScrapeSettings["sourceTypes"]) => {
    if (!scraping) return;
    void saveScraping({
      ...scraping,
      sourceTypes: { ...scraping.sourceTypes, [key]: !scraping.sourceTypes[key] },
    });
  };

  const runResearchNow = async () => {
    setStartingResearch(true);
    setScrapeError(null);
    try {
      const response = await fetch("/api/research/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Research run failed to start (${response.status})`);
      }
      setResearchStatus((current) => ({ ...(current ?? { status: "running" }), status: "running", running: true }));
    } catch (error) {
      setStartingResearch(false);
      setScrapeError(error instanceof Error ? error.message : "Could not start research.");
    }
  };

  const reviewCandidate = async (domain: string, decision: "approved" | "rejected") => {
    const response = await fetch("/api/research/sources/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, decision }),
    });
    if (!response.ok) {
      setScrapeError(`Could not ${decision === "approved" ? "approve" : "reject"} ${domain}.`);
      return;
    }
    setSourceRegistry((await response.json()) as SourceRegistryResponse);
  };

  const verifiedSources = sourceRegistry?.sources.filter((item) => item.source_class === "verified") ?? [];
  const communitySources = sourceRegistry?.sources.filter((item) => item.source_class === "community") ?? [];
  const observedSources = sourceRegistry?.observed ?? [];
  const pendingCandidates = sourceRegistry?.candidates.filter((item) => item.status === "pending") ?? [];
  const reviewedCandidates = sourceRegistry?.candidates.filter((item) => item.status !== "pending") ?? [];
  const pendingCount = pendingCandidates.length;

  const toggleProvider = (providerId: string) => {
    if (!scraping || !scraping.providerStatus[providerId]?.available) return;
    void saveScraping({
      ...scraping,
      providers: {
        ...scraping.providers,
        [providerId]: !scraping.providers[providerId],
      },
    });
  };

  const enableFullPower = () => {
    if (!scraping) return;
    const providers = { ...scraping.providers };
    Object.values(scraping.providerStatus).forEach((provider) => {
      if (provider.available) providers[provider.id] = true;
    });
    void saveScraping({ ...scraping, providers });
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-6xl flex-col px-6 py-6 sm:px-10 lg:px-12">
      <header className="pb-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-pos/15 text-pos">
            <Palette size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-txt">Settings</h1>
            <p className="text-sm text-muted">
              Control workspace appearance and dashboard preferences.
            </p>
          </div>
        </div>
      </header>

      <nav className="-mx-1 mb-5 flex gap-1 overflow-x-auto border-b border-hairline pb-px">
        {TABS.map((item) => {
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`shrink-0 border-b-2 px-3 py-2 text-sm font-semibold transition ${
                active
                  ? "border-pos text-txt"
                  : "border-transparent text-muted hover:text-txt"
              }`}
            >
              {item.label}
              {item.id === "sources" && pendingCount > 0 && (
                <span className="ml-2 rounded-full bg-pos/15 px-1.5 py-0.5 text-[10px] font-semibold text-pos">
                  {pendingCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {tab === "appearance" && (
      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.55fr)]">
        <div className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-faint">
                Appearance
              </p>
              <h2 className="mt-1 text-xl font-semibold text-txt">
                Theme mode
              </h2>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
                The setting applies across the dashboard, assistant, charts,
                inputs, panels, and sidebar. Dark mode remains the default.
              </p>
            </div>
            <span className="rounded-full border border-hairline bg-raised px-3 py-1 text-xs font-medium text-muted">
              {mode === "dark" ? "Dark active" : "Light active"}
            </span>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {OPTIONS.map((option) => {
              const active = mode === option.mode;
              return (
                <button
                  key={option.mode}
                  onClick={() => setMode(option.mode)}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? "border-pos bg-pos/10 text-txt"
                      : "border-hairline bg-canvas/50 text-muted hover:bg-raised hover:text-txt"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className={active ? "text-pos" : "text-faint"}>
                      {option.icon}
                    </span>
                    <span className="font-semibold">{option.title}</span>
                  </span>
                  <span className="mt-2 block text-sm leading-relaxed text-muted">
                    {option.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Preview
          </p>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-hairline bg-canvas/60 p-4">
              <p className="text-sm font-semibold text-txt">Dashboard card</p>
              <p className="mt-1 text-sm text-muted">
                Surfaces, borders, and text adapt from shared theme tokens.
              </p>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-raised">
                <div className="h-full w-2/3 rounded-full bg-pos" />
              </div>
            </div>
            <div className="rounded-xl bg-pos px-4 py-3 text-sm font-medium text-canvas">
              User chat bubble uses a solid accent color.
            </div>
            <div className="rounded-xl border border-hairline bg-raised px-4 py-3 text-sm text-txt">
              Assistant panels stay readable in both modes.
            </div>
          </div>
        </div>
      </section>
      )}

      {tab === "research" && (
      <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pos/15 text-pos">
              <Database size={18} />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-faint">
                Research pipeline
              </p>
              <h2 className="mt-1 text-xl font-semibold text-txt">Scraping providers</h2>
              <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
                Discovery fans out across every enabled provider. Duplicate URLs and claims are merged before verification.
              </p>
            </div>
          </div>
          <button
            onClick={enableFullPower}
            disabled={!scraping || saving}
            className="flex shrink-0 items-center justify-center gap-2 rounded-lg border border-pos/35 bg-pos/10 px-3 py-2 text-xs font-semibold text-pos transition hover:bg-pos/15 disabled:opacity-40"
          >
            <Power size={14} />
            Full power
          </button>
        </div>

        {scrapeError && (
          <p className="mt-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
            {scrapeError}
          </p>
        )}

        {!scraping ? (
          <div className="mt-5 flex items-center gap-2 text-sm text-muted">
            <LoaderCircle size={16} className="animate-spin" /> Loading provider status
          </div>
        ) : (
          <>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Object.values(scraping.providerStatus).map((provider) => {
                const active = provider.available && scraping.providers[provider.id];
                return (
                  <button
                    key={provider.id}
                    onClick={() => toggleProvider(provider.id)}
                    disabled={!provider.available || saving}
                    className={`min-h-28 rounded-xl border p-4 text-left transition ${
                      active
                        ? "border-pos bg-pos/10"
                        : provider.available
                          ? "border-hairline bg-canvas/45 hover:bg-raised"
                          : "cursor-not-allowed border-hairline bg-canvas/25 opacity-60"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-txt">{provider.label}</span>
                      <span
                        className={`flex h-5 w-5 items-center justify-center rounded-md border ${
                          active ? "border-pos bg-pos text-canvas" : "border-hairline text-transparent"
                        }`}
                      >
                        <Check size={13} />
                      </span>
                    </span>
                    <span className={`mt-3 block text-xs ${provider.available ? "text-muted" : "text-faint"}`}>
                      {provider.available
                        ? active
                          ? "Enabled for search and retrieval"
                          : "Configured and ready"
                        : provider.reason || "Not configured"}
                    </span>
                  </button>
                );
              })}
            </div>

            <SelfHostedScrapers
              searxngBaseUrl={scraping.searxngBaseUrl}
              crawl4aiBaseUrl={scraping.crawl4aiBaseUrl}
              saving={saving}
              onSave={(patch) => void saveScraping({ ...scraping, ...patch })}
            />

            <div className="mt-5 border-t border-hairline pt-5">
              <div className="flex items-center gap-2">
                <ShieldCheck size={15} className="text-pos" />
                <p className="text-xs font-semibold uppercase tracking-wider text-faint">Source coverage</p>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Source reputation and claim verification are tracked separately. Community sources influence only the live sentiment signal by at most two points.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {([
                  ["verified", "Verified", "Official, regulatory, standards, and approved reporting sources"],
                  ["nonVerified", "Non-verified", "Broader web coverage retained with a clear trust label"],
                  ["community", "Community sentiment", "Reddit and similar discussion signals, never core evidence"],
                ] as const).map(([key, label, description]) => {
                  const active = scraping.sourceTypes[key];
                  return (
                    <button
                      key={key}
                      onClick={() => toggleSourceType(key)}
                      disabled={saving}
                      className={`rounded-xl border p-3 text-left transition ${
                        active ? "border-pos/60 bg-pos/10" : "border-hairline bg-canvas/35"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-txt">{label}</span>
                        <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${
                          active ? "border-pos bg-pos text-canvas" : "border-hairline text-transparent"
                        }`}>
                          <Check size={13} />
                        </span>
                      </span>
                      <span className="mt-2 block text-xs leading-relaxed text-muted">{description}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-5 grid gap-4 border-t border-hairline pt-5 md:grid-cols-[minmax(0,1fr)_minmax(260px,0.6fr)]">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-faint">Schedule</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {FREQUENCIES.map((frequency) => (
                    <button
                      key={frequency}
                      onClick={() => void saveScraping({ ...scraping, frequency })}
                      disabled={saving}
                      className={`rounded-lg border px-3 py-2 text-xs font-semibold capitalize transition ${
                        scraping.frequency === frequency
                          ? "border-pos bg-pos/10 text-pos"
                          : "border-hairline bg-canvas/45 text-muted hover:text-txt"
                      }`}
                    >
                      {frequency}
                    </button>
                  ))}
                </div>
                <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-faint">Companies per run</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {COMPANY_COUNTS.map((count) => (
                    <button
                      key={count}
                      onClick={() => void saveScraping({ ...scraping, maxCompanies: count })}
                      disabled={saving}
                      className={`rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                        scraping.maxCompanies === count
                          ? "border-pos bg-pos/10 text-pos"
                          : "border-hairline bg-canvas/45 text-muted hover:text-txt"
                      }`}
                    >
                      {count}
                    </button>
                  ))}
                  <label className="flex items-center gap-1.5 text-[11px] text-faint">
                    custom
                    <input
                      type="number"
                      min={1}
                      max={50}
                      defaultValue={scraping.maxCompanies}
                      onBlur={(event) => {
                        const value = Number(event.target.value);
                        if (Number.isFinite(value) && value >= 1 && value <= 50 && value !== scraping.maxCompanies) {
                          void saveScraping({ ...scraping, maxCompanies: Math.round(value) });
                        }
                      }}
                      disabled={saving}
                      className="w-16 rounded-lg border border-hairline bg-canvas/45 px-2 py-1.5 text-xs text-txt"
                    />
                  </label>
                </div>
                <p className="mt-1.5 text-[11px] text-faint">
                  Scheduled and manual runs cover the first {scraping.maxCompanies} companies of the universe (max 50).
                </p>
              </div>
              <div className="space-y-3 rounded-xl border border-hairline bg-canvas/45 px-4 py-3 text-xs leading-relaxed text-muted">
                <p>
                  Runs at <span className="font-semibold text-txt">{scraping.runAt} Singapore time</span>. Raw pages are retained for {scraping.retainRawDays} days; extracted claims and provenance are retained.
                </p>
                <button
                  onClick={() => void runResearchNow()}
                  disabled={startingResearch || researchStatus?.running}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-pos px-3 py-2 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-45"
                >
                  {startingResearch || researchStatus?.running ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Play size={14} />
                  )}
                  {startingResearch || researchStatus?.running ? "Research running" : `Run ${scraping.maxCompanies} companies now`}
                </button>
                {researchStatus && researchStatus.status !== "never_run" && (
                  <p className="text-[11px] text-faint">
                    Latest: {researchStatus.status} · {researchStatus.source_count ?? 0} sources · {researchStatus.claim_count ?? 0} grouped claims
                  </p>
                )}
              </div>
            </div>
          </>
        )}
      </section>
      )}

      {tab === "models" && <ModelProviderPanel />}

      {tab === "feedback" && <FeedbackPanel />}

      {tab === "sources" && (
      <div className="space-y-5 pb-5">
      <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pos/15 text-pos">
            <ShieldCheck size={18} />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">Source registry</p>
            <h2 className="mt-1 text-xl font-semibold text-txt">Domains by trust class</h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
              Verified and community domains are seeded from the built-in registry and extended by approved promotions. Any other domain a run fetches is treated as non-verified by default.
            </p>
          </div>
        </div>

        {!sourceRegistry ? (
          <div className="mt-5 flex items-center gap-2 text-sm text-muted">
            <LoaderCircle size={15} className="animate-spin" /> Loading source registry
          </div>
        ) : (
          <div className="mt-5 grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-hairline bg-canvas/40 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-txt">
                  <ShieldCheck size={14} className="text-pos" /> Verified
                </span>
                <span className="text-xs text-faint">{verifiedSources.length}</span>
              </div>
              <ul className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {verifiedSources.map((item) => (
                  <li key={item.domain} className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-xs text-txt" title={item.reason ?? undefined}>
                      {item.domain}
                    </span>
                    {!item.is_builtin && (
                      <span className="shrink-0 text-[10px] font-semibold uppercase text-pos">promoted</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-xl border border-hairline bg-canvas/40 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-sm font-semibold text-txt">
                  <Globe size={14} className="text-faint" /> Non-verified in use
                </span>
                <span className="text-xs text-faint">{observedSources.length}</span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-faint">
                Observed in cached pages, not a fixed list.
              </p>
              <ul className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {observedSources.map((item) => (
                  <li key={item.domain} className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-xs text-txt">{item.domain}</span>
                    <span className="shrink-0 text-[10px] text-faint">{item.pages}</span>
                  </li>
                ))}
                {observedSources.length === 0 && (
                  <li className="text-xs text-muted">No cached non-verified pages yet.</li>
                )}
              </ul>
            </div>

            <div className="rounded-xl border border-hairline bg-canvas/40 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-txt">Community</span>
                <span className="text-xs text-faint">{communitySources.length}</span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-faint">
                Sentiment signal only, capped at two points.
              </p>
              <ul className="mt-3 space-y-1.5">
                {communitySources.map((item) => (
                  <li key={item.domain} className="truncate text-xs text-txt">{item.domain}</li>
                ))}
              </ul>
              {reviewedCandidates.length > 0 && (
                <>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-faint">
                    Reviewed
                  </p>
                  <ul className="mt-2 max-h-40 space-y-1.5 overflow-y-auto pr-1">
                    {reviewedCandidates.map((item) => (
                      <li key={item.domain} className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-xs text-txt">{item.domain}</span>
                        <span className={`shrink-0 text-[10px] font-semibold uppercase ${
                          item.status === "approved" ? "text-pos" : "text-muted"
                        }`}>
                          {item.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">Trust governance</p>
            <h2 className="mt-1 text-xl font-semibold text-txt">Source promotion</h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">
              A non-verified domain appears here only after multiple claims overlap with at least two verified domains. Approval promotes the domain, not every claim it publishes.
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-hairline bg-canvas/45 px-3 py-1 text-xs text-muted">
            {pendingCount} pending
          </span>
        </div>
        <div className="mt-4 space-y-2">
          {pendingCandidates.map((candidate) => (
            <div key={candidate.domain} className="flex flex-col gap-3 rounded-xl border border-hairline bg-canvas/40 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-txt">{candidate.domain}</p>
                <p className="mt-1 text-xs text-muted">
                  {candidate.matching_claims} matching claims · {Math.round(candidate.overlap_score * 100)}% overlap · {candidate.matched_verified_domains.join(", ")}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button onClick={() => void reviewCandidate(candidate.domain, "rejected")} className="rounded-lg border border-hairline px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-txt">
                  Reject
                </button>
                <button onClick={() => void reviewCandidate(candidate.domain, "approved")} className="rounded-lg bg-pos px-3 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105">
                  Approve
                </button>
              </div>
            </div>
          ))}
          {sourceRegistry && pendingCount === 0 && (
            <div className="rounded-xl border border-dashed border-hairline p-4 text-sm text-muted">
              No domains currently meet the promotion threshold.
            </div>
          )}
          {!sourceRegistry && (
            <div className="flex items-center gap-2 py-2 text-sm text-muted">
              <LoaderCircle size={15} className="animate-spin" /> Loading source registry
            </div>
          )}
        </div>
      </section>
      </div>
      )}
    </div>
  );
}
