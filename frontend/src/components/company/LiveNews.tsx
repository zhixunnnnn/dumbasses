import { ExternalLink, Radio } from "lucide-react";
import { api, useApi } from "../../lib/api";

const LABEL_COLOR: Record<string, string> = {
  controversy: "#ec6a5e",
  positive: "#3ecf8e",
  neutral: "#9a968e",
};

export default function LiveNews({ companyId }: { companyId: string }) {
  const { data } = useApi(api.news, []);
  const entry = data?.companies?.find((c) => c.company_id === companyId);
  if (!entry || entry.n_items === 0) return null;

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio size={15} className="text-purpose" />
          <div>
            <h3 className="text-sm font-semibold text-txt">Live news signal</h3>
            <p className="text-[11px] text-faint">
              Scraped via <span className="text-purpose">Bright Data</span> · Bing News (current, outside the 2019–2023 evidence window)
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-semibold"
            style={{ color: entry.sentiment >= 0 ? "#3ecf8e" : "#ec6a5e" }}>
            {entry.sentiment >= 0 ? "+" : ""}{entry.sentiment}
          </p>
          <p className="text-[10px] text-faint">{entry.positive} pos · {entry.controversy} controversy</p>
        </div>
      </div>
      <div className="mt-3 space-y-1.5">
        {entry.headlines.map((h, i) => (
          <a key={i} href={h.url ?? "#"} target="_blank" rel="noreferrer"
            className="group flex items-start gap-2 rounded-md px-2 py-1.5 transition hover:bg-raised/50">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: LABEL_COLOR[h.label] }} />
            <span className="flex-1 text-[12px] leading-snug text-muted group-hover:text-txt">{h.title}</span>
            <ExternalLink size={12} className="mt-0.5 shrink-0 text-faint opacity-0 group-hover:opacity-100" />
          </a>
        ))}
      </div>
    </div>
  );
}
