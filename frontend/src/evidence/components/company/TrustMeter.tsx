import type { Raters } from "../../types";
import { na } from "../../lib/ui";

const RATERS: { key: keyof Raters; label: string; color: string }[] = [
  { key: "msci_pct", label: "MSCI", color: "#4cc4d4" },
  { key: "sp_pct", label: "S&P", color: "#e0b24a" },
  { key: "sustainalytics_pct", label: "Sustainalytics", color: "#a78bfa" },
];

export default function TrustMeter({ raters }: { raters: Raters }) {
  const vals = RATERS
    .map((r) => ({
      ...r,
      v: raters[r.key] as number | null,
      real: r.key === "msci_pct" ? Boolean(raters.msci_real) : false,
    }))
    .filter((r) => r.v !== null);

  const div = raters.divergence;
  const trust =
    div === null ? { label: "Single rater", color: "#6a665f" }
      : div > 33 ? { label: "High disagreement", color: "#ec6a5e" }
        : div > 15 ? { label: "Moderate disagreement", color: "#e0b24a" }
          : { label: "Raters aligned", color: "#3ecf8e" };

  const anyReal = vals.some((r) => r.real);
  const lo = vals.length ? Math.min(...vals.map((r) => r.v as number)) : 0;
  const hi = vals.length ? Math.max(...vals.map((r) => r.v as number)) : 0;

  return (
    <div>
      <div className="relative mt-1 h-9">
        <div className="absolute left-0 right-0 top-4 h-1 rounded bg-raised" />
        {vals.length >= 2 && (
          <div className="absolute top-4 h-1 rounded" style={{
            left: `${lo}%`, width: `${hi - lo}%`, backgroundColor: trust.color, opacity: 0.4,
          }} />
        )}
        {vals.map((r) => (
          <div key={r.label} className="group absolute -translate-x-1/2" style={{ left: `${r.v}%`, top: 0 }}>
            <div className="mx-auto h-4 w-0.5" style={{ backgroundColor: r.color }} />
            {/* solid marker = real (scraped); hollow marker = illustrative */}
            <div
              className="h-2.5 w-2.5 rounded-full ring-2 ring-surface"
              style={r.real
                ? { backgroundColor: r.color }
                : { backgroundColor: "transparent", border: `1.5px solid ${r.color}` }}
              title={`${r.label}: ${r.v} (${r.real ? "real" : "illustrative"})`}
            />
          </div>
        ))}
      </div>

      <div className="mt-1 flex items-center justify-between">
        <div className="flex flex-wrap gap-3">
          {vals.map((r) => (
            <span key={r.label} className="inline-flex items-center gap-1 text-[10.5px] text-muted">
              <span className="h-2 w-2 rounded-full"
                style={r.real ? { backgroundColor: r.color } : { backgroundColor: "transparent", border: `1.5px solid ${r.color}` }} />
              {r.label} {na(r.v, 0)}
              <span className={r.real ? "text-pos" : "text-faint"}>{r.real ? "· real" : "· illus."}</span>
            </span>
          ))}
        </div>
        <span className="text-[11px] font-medium" style={{ color: trust.color }}>
          {trust.label}{anyReal ? "" : ""}
        </span>
      </div>

      <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[10px] leading-snug text-faint">
        <span><span className="text-muted">●</span> real (scraped) · <span className="text-muted">○</span> illustrative.</span>
        {raters.msci_real ? (
          <span>
            MSCI:{" "}
            {raters.msci_url ? (
              <a href={raters.msci_url} target="_blank" rel="noreferrer" className="text-pos hover:underline">
                real ({raters.msci_source || "external"})
              </a>
            ) : (
              <span className="text-pos">real ({raters.msci_source || "external"})</span>
            )}{" "}
            · S&amp;P &amp; Sustainalytics illustrative · divergence partly real.
          </span>
        ) : (
          <span>Rater scores illustrative (for demo).</span>
        )}
      </p>
    </div>
  );
}
