import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { HelpCircle, Quote, X } from "lucide-react";
import type { TraceNode } from "../../types";

function hasSentence(node: TraceNode): boolean {
  return Boolean(node.source_sentence) || node.children.some(hasSentence);
}

function NodeView({ node, depth }: { node: TraceNode; depth: number }) {
  return (
    <div className={depth === 0 ? "" : "border-l border-hairline pl-3"}>
      <div className="flex items-start gap-2 py-1">
        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-faint" />
        <div className="min-w-0">
          <p className="text-[12.5px] leading-snug text-txt">
            {node.label}
            {node.value !== null && (
              <span className="ml-1.5 font-mono text-[11px] text-muted">
                = {node.value}
              </span>
            )}
            {node.contribution !== null && (
              <span className="ml-1.5 font-mono text-[11px] text-faint">
                (+{node.contribution})
              </span>
            )}
          </p>
          {node.source_sentence && (
            <div className="mt-1 flex gap-1.5 rounded-md border border-pos/25 bg-pos/[0.06] px-2 py-1.5">
              <Quote size={12} className="mt-0.5 shrink-0 text-pos" />
              <p className="text-[12px] italic leading-snug text-muted">
                “{node.source_sentence}”
                {node.source_doc && (
                  <span className="ml-1 not-italic text-faint">
                    — {node.source_doc}
                    {node.source_page ? `, p.${node.source_page}` : ""}
                  </span>
                )}
              </p>
            </div>
          )}
        </div>
      </div>
      {node.children.length > 0 && (
        <div className="ml-1.5">
          {node.children.map((c, i) => (
            <NodeView key={i} node={c} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Why({
  trace,
  title = "Why?",
  className = "",
}: {
  trace: TraceNode;
  title?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const traceable = hasSentence(trace);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Trace this number to its source"
        className={`inline-flex items-center gap-1 rounded-md border border-hairline px-1.5 py-0.5 text-[10px] font-medium text-muted transition hover:border-pos/40 hover:text-pos ${className}`}
      >
        <HelpCircle size={11} />
        why?
      </button>
      {open && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-hairline bg-surface shadow-float"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 flex items-center justify-between border-b border-hairline bg-surface px-4 py-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-txt">{title}</p>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    traceable ? "bg-pos/15 text-pos" : "bg-raised text-faint"
                  }`}
                >
                  {traceable ? "traces to source" : "data-derived"}
                </span>
              </div>
              <button onClick={() => setOpen(false)} className="text-muted hover:text-txt">
                <X size={16} />
              </button>
            </div>
            <div className="px-4 py-3">
              <NodeView node={trace} depth={0} />
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
