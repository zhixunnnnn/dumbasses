import { useState } from "react";
import { ExternalLink, Quote, Radio, Sparkles } from "lucide-react";
import type { ClaimRow } from "../../types";
import { TOPIC_LABEL } from "../../lib/ui";
import { StateBadge } from "../common/badges";

export default function ClaimTable({
  claims,
  absent,
  live,
  sourceUrl,
  sourceTitle,
}: {
  claims: ClaimRow[];
  absent: { topic_id: string; state: string }[];
  live?: boolean;
  sourceUrl?: string;
  sourceTitle?: string;
}) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-txt">Claims &amp; evidence</h3>
          <p className="text-[11px] text-faint">
            Each claim verified against the most authoritative source. Absence lowers confidence, never the score.
          </p>
        </div>
        {live && sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            title={sourceTitle || "Source report"}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-pos/30 bg-pos/10 px-2.5 py-1 text-[10px] font-semibold text-pos transition hover:bg-pos/15"
          >
            <Radio size={11} /> LIVE · from report
            <ExternalLink size={11} />
          </a>
        )}
      </div>
      <div className="divide-y divide-hairline/60">
        {claims.map((c, i) => (
          <div key={i}>
            <button
              onClick={() => setOpen(open === i ? null : i)}
              className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition hover:bg-raised/40"
            >
              <StateBadge state={c.state} />
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] leading-snug text-txt">{c.text}</p>
                <p className="mt-0.5 text-[10px] text-faint">
                  {TOPIC_LABEL(c.topic_id)} · pillar {c.pillar} · weight {c.weight}
                </p>
              </div>
              {c.state === "INFERRED" ? (
                <Sparkles size={13} className="mt-0.5 shrink-0" style={{ color: "#a78bfa" }} />
              ) : (
                <Quote size={13} className="mt-0.5 shrink-0 text-faint" />
              )}
            </button>
            {open === i && c.state === "INFERRED" && (
              <div
                className="mx-4 mb-3 flex gap-2 rounded-md border px-3 py-2"
                style={{ borderColor: "#a78bfa55", backgroundColor: "#a78bfa14" }}
              >
                <Sparkles size={12} className="mt-0.5 shrink-0" style={{ color: "#a78bfa" }} />
                <p className="text-[12px] leading-snug text-muted">
                  Inferred — this material topic isn’t directly disclosed in the report. This is an
                  AI best-estimate from the full report and sector norms, shown for completeness and
                  scored at reduced weight (not counted as a verified disclosure).
                  {c.source_url && (
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-1 inline-flex items-center gap-0.5 text-pos hover:underline"
                    >
                      {c.source_doc}
                      <ExternalLink size={10} />
                    </a>
                  )}
                </p>
              </div>
            )}
            {open === i && c.source_sentence && (
              <div className="mx-4 mb-3 flex gap-2 rounded-md border border-pos/25 bg-pos/[0.06] px-3 py-2">
                <Quote size={12} className="mt-0.5 shrink-0 text-pos" />
                <p className="text-[12px] italic leading-snug text-muted">
                  “{c.source_sentence}”
                  {c.source_doc && (
                    <span className="ml-1 not-italic text-faint">
                      —{" "}
                      {c.source_url ? (
                        <a
                          href={c.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-0.5 text-pos hover:underline"
                        >
                          {c.source_doc}
                          <ExternalLink size={10} />
                        </a>
                      ) : (
                        c.source_doc
                      )}
                      {c.source_page ? `, p.${c.source_page}` : ""}
                    </span>
                  )}
                </p>
              </div>
            )}
            {open === i && c.corroboration_url && (
              <div className="mx-4 mb-3 flex gap-2 rounded-md border border-pos/40 bg-pos/[0.1] px-3 py-2">
                <Radio size={12} className="mt-0.5 shrink-0 text-pos" />
                <p className="text-[12px] leading-snug text-muted">
                  Independently corroborated by{" "}
                  <a
                    href={c.corroboration_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-0.5 font-medium text-pos hover:underline"
                  >
                    {c.corroboration_source || "an external source"}
                    <ExternalLink size={10} />
                  </a>{" "}
                  — raised from company-disclosed to verified.
                </p>
              </div>
            )}
          </div>
        ))}
        {absent.map((a) => (
          <div key={a.topic_id} className="flex items-center gap-3 px-4 py-2.5 opacity-70">
            <StateBadge state="ABSENT" />
            <p className="text-[12.5px] text-faint">
              {TOPIC_LABEL(a.topic_id)} — <span className="italic">material topic, undisclosed</span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
