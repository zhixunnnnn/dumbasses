import { ExternalLink, Newspaper, Radio, ArrowRight } from "lucide-react";
import { api, useApi } from "../../lib/api";
import type { NewsCompany } from "../../types";
import { useNavigation } from "../../navigation/NavigationContext";

const LABEL_COLOR: Record<string, string> = {
  controversy: "#ec6a5e",
  positive: "#3ecf8e",
  stock: "#6ea8fe",
  neutral: "#9a968e",
};

function Stat({ value, label, accent }: { value: number | string; label: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-4 py-2.5">
      <p className="text-xl font-semibold" style={{ color: accent }}>{value}</p>
      <p className="text-[11px] text-faint">{label}</p>
    </div>
  );
}

function CompanyNews({ c, onOpen }: { c: NewsCompany; onOpen: (id: string) => void }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="mb-2 flex items-center justify-between">
        <button onClick={() => onOpen(c.company_id)}
          className="group flex items-center gap-1.5 text-left">
          <span className="text-sm font-semibold text-txt group-hover:text-pos">{c.name}</span>
          <ArrowRight size={13} className="text-faint transition group-hover:text-pos" />
        </button>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="font-mono font-semibold"
            style={{ color: c.sentiment >= 0 ? "#3ecf8e" : "#ec6a5e" }}>
            sentiment {c.sentiment >= 0 ? "+" : ""}{c.sentiment}
          </span>
          {c.controversy > 0 && <span className="text-neg">· {c.controversy} controversy</span>}
        </div>
      </div>
      <div className="space-y-1">
        {c.headlines.length === 0 && <p className="text-[12px] text-faint">No recent coverage.</p>}
        {c.headlines.map((h, i) => (
          <a key={i} href={h.url ?? "#"} target="_blank" rel="noreferrer"
            className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition hover:bg-raised/50">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: LABEL_COLOR[h.label] }} />
            <span className="flex-1 text-[12.5px] leading-snug text-muted group-hover:text-txt">{h.title}</span>
            <ExternalLink size={12} className="mt-0.5 shrink-0 text-faint opacity-0 group-hover:opacity-100" />
          </a>
        ))}
      </div>
    </div>
  );
}

export default function NewsPage() {
  const { openCompany } = useNavigation();
  const { data, loading, error } = useApi(api.news, []);

  if (loading) return <div className="p-10 text-sm text-muted">Loading live news…</div>;
  if (error || !data) return <div className="p-10 text-sm text-neg">Couldn’t load news. {error}</div>;

  const companies = [...data.companies].sort(
    (a, b) => b.controversy - a.controversy || a.sentiment - b.sentiment,
  );
  const totalItems = companies.reduce((s, c) => s + c.n_items, 0);
  const totalControversy = companies.reduce((s, c) => s + c.controversy, 0);
  const totalPositive = companies.reduce((s, c) => s + c.positive, 0);
  const totalStock = companies.reduce(
    (s, c) => s + c.headlines.filter((h) => h.label === "stock").length, 0,
  );

  return (
    <div className="mx-auto max-w-[1100px] space-y-5 p-5 md:p-7">
      <header>
        <div className="flex items-center gap-2 text-pos">
          <Newspaper size={16} />
          <p className="text-[11px] font-semibold uppercase tracking-wider">Alternative data · live</p>
        </div>
        <h1 className="mt-1 text-2xl font-semibold text-txt">What the market is saying</h1>
        <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-muted">
          <Radio size={13} className="text-purpose" />
          Scraped via <span className="text-purpose">Bright Data</span> · Bing News · refreshed weekly
          (Mondays){data.last_run ? ` · last ${data.last_run.slice(0, 10)}` : ""}. Click any headline to open the source.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Stat value={companies.length} label="companies tracked" />
          <Stat value={totalItems} label="ESG + stock headlines" />
          <Stat value={totalPositive} label="positive ESG" accent="#3ecf8e" />
          <Stat value={totalStock} label="stock / market" accent="#6ea8fe" />
          <Stat value={totalControversy} label="controversy flags" accent="#ec6a5e" />
        </div>
        <div className="mt-3 flex gap-4 text-[11px] text-faint">
          {Object.entries(LABEL_COLOR).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: v }} />{k}
            </span>
          ))}
        </div>
      </header>

      {companies.length === 0 ? (
        <div className="rounded-xl border border-hairline bg-surface p-8 text-center text-sm text-faint">
          No news scraped yet. Run <code className="text-muted">python -m backend.data.scrape --news</code>.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {companies.map((c) => (
            <CompanyNews key={c.company_id} c={c} onOpen={openCompany} />
          ))}
        </div>
      )}
    </div>
  );
}
