import { useMemo, useState } from "react";
import { ExternalLink, Newspaper, Radio, ArrowRight, Search, X } from "lucide-react";
import { api, useApi } from "../../lib/api";
import type { NewsCompany, NewsItem } from "../../types";
import { useNavigation } from "../../navigation/NavigationContext";

const LABEL_COLOR: Record<string, string> = {
  controversy: "#ec6a5e",
  positive: "#3ecf8e",
  stock: "#6ea8fe",
  neutral: "#9a968e",
};
const LABEL_TEXT: Record<string, string> = {
  controversy: "Controversy",
  positive: "ESG +",
  stock: "Stock",
  neutral: "ESG",
};

type Topic = "All" | "ESG" | "Stock";

function domain(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function Stat({ value, label, accent }: { value: number | string; label: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3.5 py-2">
      <p className="text-lg font-semibold leading-none" style={{ color: accent }}>{value}</p>
      <p className="mt-1 text-[10.5px] text-faint">{label}</p>
    </div>
  );
}

function Headline({ h, q }: { h: NewsItem; q: string }) {
  const color = LABEL_COLOR[h.label];
  const d = domain(h.url);
  return (
    <a href={h.url ?? "#"} target="_blank" rel="noreferrer"
      className="group flex items-start gap-2.5 rounded-lg border border-transparent px-2.5 py-2 transition hover:border-hairline hover:bg-raised/50">
      <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <div className="min-w-0 flex-1">
        <p className="text-[12.5px] leading-snug text-muted group-hover:text-txt">
          {highlight(h.title, q)}
        </p>
        <div className="mt-1 flex items-center gap-2 text-[10px] text-faint">
          <span className="rounded px-1 py-px font-medium" style={{ color, backgroundColor: `${color}1a` }}>
            {LABEL_TEXT[h.label]}
          </span>
          {d && <span>{d}</span>}
        </div>
      </div>
      <ExternalLink size={12} className="mt-0.5 shrink-0 text-faint opacity-0 transition group-hover:opacity-100" />
    </a>
  );
}

function highlight(text: string, q: string) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-pos/25 text-txt">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

function CompanyCard({ c, headlines, q, onOpen }: {
  c: NewsCompany; headlines: NewsItem[]; q: string; onOpen: (id: string) => void;
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-3.5 shadow-panel">
      <div className="mb-2 flex items-start justify-between gap-2">
        <button onClick={() => onOpen(c.company_id)} className="group min-w-0 text-left">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-txt group-hover:text-pos">{c.name}</span>
            <ArrowRight size={13} className="shrink-0 text-faint transition group-hover:text-pos" />
          </div>
          <p className="font-mono text-[10px] text-faint">{c.ticker} · {c.sector}</p>
        </button>
        <div className="shrink-0 text-right">
          <span className="font-mono text-[12px] font-semibold"
            style={{ color: c.sentiment > 0 ? "#3ecf8e" : c.sentiment < 0 ? "#ec6a5e" : "#9a968e" }}>
            {c.sentiment >= 0 ? "+" : ""}{c.sentiment}
          </span>
          {c.controversy > 0 && <p className="text-[10px] text-neg">{c.controversy} controversy</p>}
        </div>
      </div>
      <div className="space-y-0.5">
        {headlines.map((h, i) => <Headline key={i} h={h} q={q} />)}
      </div>
    </div>
  );
}

export default function NewsPage() {
  const { openCompany } = useNavigation();
  const { data, loading, error } = useApi(api.news, []);
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("All");
  const [topic, setTopic] = useState<Topic>("All");

  const sectors = useMemo(() => {
    const s = new Set<string>();
    data?.companies.forEach((c) => c.sector && s.add(c.sector));
    return ["All", ...[...s].sort()];
  }, [data]);

  if (loading) return <div className="p-10 text-sm text-muted">Loading live news…</div>;
  if (error || !data) return <div className="p-10 text-sm text-neg">Couldn’t load news. {error}</div>;

  const query = q.trim().toLowerCase();
  const view = data.companies
    .filter((c) => sector === "All" || c.sector === sector)
    .map((c) => {
      let hs = c.headlines;
      if (topic === "ESG") hs = hs.filter((h) => h.label !== "stock");
      if (topic === "Stock") hs = hs.filter((h) => h.label === "stock");
      const nameMatch = query && (c.name.toLowerCase().includes(query) ||
        (c.ticker ?? "").toLowerCase().includes(query));
      const shown = query && !nameMatch ? hs.filter((h) => h.title.toLowerCase().includes(query)) : hs;
      return { c, shown, include: shown.length > 0 || Boolean(nameMatch) };
    })
    .filter((x) => x.include);

  const allShown = view.flatMap((x) => x.shown);
  const stat = {
    companies: view.length,
    headlines: allShown.length,
    stock: allShown.filter((h) => h.label === "stock").length,
    positive: allShown.filter((h) => h.label === "positive").length,
    controversy: allShown.filter((h) => h.label === "controversy").length,
  };

  return (
    <div className="mx-auto max-w-[1140px] space-y-4 p-5 md:p-7">
      <header>
        <div className="flex items-center gap-2 text-pos">
          <Newspaper size={16} />
          <p className="text-[11px] font-semibold uppercase tracking-wider">Alternative data · live</p>
        </div>
        <h1 className="mt-1 text-2xl font-semibold text-txt">What the market is saying</h1>
        <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
          <Radio size={13} className="text-purpose" />
          Company-specific ESG &amp; stock news scraped via <span className="text-purpose">Bright Data</span> ·
          refreshed weekly (Mondays){data.last_run ? ` · last ${data.last_run.slice(0, 10)}` : ""}.
          Click any headline to open the source.
        </p>
      </header>

      {/* filter bar */}
      <div className="sticky top-0 z-10 -mx-1 space-y-2.5 rounded-xl border border-hairline bg-surface/95 p-3 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search companies or headlines…"
              className="w-full rounded-lg border border-hairline bg-canvas/60 py-1.5 pl-8 pr-7 text-[13px] text-txt placeholder:text-faint focus:border-pos/50 focus:outline-none"
            />
            {q && (
              <button onClick={() => setQ("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-faint hover:text-txt">
                <X size={13} />
              </button>
            )}
          </div>
          <div className="flex rounded-lg border border-hairline bg-canvas/40 p-0.5">
            {(["All", "ESG", "Stock"] as Topic[]).map((t) => (
              <button key={t} onClick={() => setTopic(t)}
                className={`rounded-md px-2.5 py-1 text-[12px] transition ${
                  topic === t ? "bg-raised text-txt" : "text-muted hover:text-txt"
                }`}>
                {t}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {sectors.map((s) => (
            <button key={s} onClick={() => setSector(s)}
              className={`rounded-full border px-2.5 py-0.5 text-[11.5px] transition ${
                sector === s
                  ? "border-pos/50 bg-pos/15 text-pos"
                  : "border-hairline text-muted hover:bg-raised/60 hover:text-txt"
              }`}>
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2.5">
        <Stat value={stat.companies} label="companies" />
        <Stat value={stat.headlines} label="headlines" />
        <Stat value={stat.positive} label="ESG +" accent="#3ecf8e" />
        <Stat value={stat.stock} label="stock / market" accent="#6ea8fe" />
        <Stat value={stat.controversy} label="controversy" accent="#ec6a5e" />
      </div>

      {view.length === 0 ? (
        <div className="rounded-xl border border-hairline bg-surface p-10 text-center text-sm text-faint">
          No headlines match your filters.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {view.map(({ c, shown }) => (
            <CompanyCard key={c.company_id} c={c} headlines={shown} q={query} onOpen={openCompany} />
          ))}
        </div>
      )}
    </div>
  );
}
