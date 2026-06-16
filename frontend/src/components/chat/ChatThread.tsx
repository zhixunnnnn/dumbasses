import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowUp,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Newspaper,
  Search,
  Square,
  SquareCheck,
  Wrench,
  X,
} from "lucide-react";
import {
  suggestionsForSurface,
  useChat,
  type ChatMessage,
  type ChatSurface,
  type ReferenceArticle,
  type ReportArtifact,
  type WorkflowStep,
} from "./useChat";
import { useAssistantPageContext } from "./PageContext";

type Props = {
  compact?: boolean;
  surface?: ChatSurface;
};

export default function ChatThread({ compact = false, surface = "page" }: Props) {
  const { messages, pending, activeWorkflowSteps, send, stop } =
    useChat(surface);
  const pageContext = useAssistantPageContext();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending, activeWorkflowSteps]);

  const submit = () => {
    send(draft, pageContext);
    setDraft("");
  };

  // Prefill the input with a suggestion so the user can edit before sending.
  const useSuggestion = (text: string) => {
    setDraft(text);
    textareaRef.current?.focus();
  };

  const suggestions = suggestionsForSurface(surface);
  const showSuggestions = messages.length <= 1;

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-2 py-2 sm:px-4">
        {messages.map((m) => (
          <Bubble key={m.id} message={m} compact={compact} />
        ))}
        {pending && (
          <ToolActivity compact={compact} steps={activeWorkflowSteps} />
        )}
        {showSuggestions && (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => useSuggestion(s)}
                className="rounded-full border border-hairline bg-surface px-3 py-1.5 text-xs text-muted transition hover:border-pos/40 hover:text-txt"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="mt-2 flex items-end gap-2 rounded-xl border border-hairline bg-surface p-2">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Ask about any company, sector, or signal..."
          className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-faint"
        />
        {pending ? (
          <button
            onClick={stop}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-neg text-canvas transition hover:brightness-110"
            aria-label="Stop generating"
            title="Stop generating"
          >
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!draft.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-pos text-canvas transition disabled:opacity-30"
            aria-label="Send"
          >
            <ArrowUp size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

function Bubble({
  message,
  compact,
}: {
  message: ChatMessage;
  compact: boolean;
}) {
  const isUser = message.role === "user";
  return (
    <div
      className={`flex ${
        isUser ? "justify-end pr-1 sm:pr-3" : "justify-start pl-1 sm:pl-3"
      }`}
    >
      <div
        className={`${bubbleWidth(compact, isUser)} rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed shadow-panel ${
          isUser
            ? "bg-pos text-canvas"
            : "border border-hairline bg-surface text-txt"
        }`}
      >
        {!isUser && (
          <span className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-pos">
            Copilot
          </span>
        )}
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <MarkdownContent content={message.content} />
        )}
        {!isUser && <MessageArtifacts message={message} />}
      </div>
    </div>
  );
}

function bubbleWidth(compact: boolean, isUser: boolean) {
  if (compact) {
    return isUser ? "max-w-[82%]" : "max-w-[88%]";
  }
  return isUser ? "max-w-[min(560px,68%)]" : "max-w-[min(920px,82%)]";
}

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "rule" }
  | { type: "code"; text: string };

function MarkdownContent({ content }: { content: string }) {
  const blocks = parseMarkdown(stripDecorativeSymbols(content));
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => (
        <MarkdownBlockView key={i} block={block} />
      ))}
    </div>
  );
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  if (block.type === "heading") {
    const Tag = block.level <= 2 ? "h3" : "h4";
    return (
      <Tag className="mt-2 font-semibold leading-snug text-txt first:mt-0">
        {renderInline(block.text)}
      </Tag>
    );
  }
  if (block.type === "quote") {
    return (
      <blockquote className="border-l-2 border-pos/40 pl-3 text-muted">
        {renderInline(block.text)}
      </blockquote>
    );
  }
  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag className={`space-y-1 pl-4 ${block.ordered ? "list-decimal" : "list-disc"}`}>
        {block.items.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </Tag>
    );
  }
  if (block.type === "table") {
    return (
      <div className="overflow-hidden rounded-lg border border-hairline">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="bg-canvas/60 text-muted">
            <tr>
              {block.headers.map((header, i) => (
                <th key={i} className="border-b border-hairline px-2 py-1.5 font-semibold">
                  {renderInline(header)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-canvas/25">
                {block.headers.map((_, cellIndex) => (
                  <td key={cellIndex} className="border-t border-hairline px-2 py-1.5">
                    {renderInline(row[cellIndex] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.type === "rule") {
    return <hr className="border-hairline" />;
  }
  if (block.type === "code") {
    return (
      <pre className="overflow-x-auto rounded-lg border border-hairline bg-canvas/60 p-2 font-mono text-[11px] text-muted">
        {block.text}
      </pre>
    );
  }
  return <p className="text-txt">{renderInline(block.text)}</p>;
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      blocks.push({ type: "code", text: code.join("\n") });
      i += 1;
      continue;
    }

    if (/^---+$/.test(line)) {
      blocks.push({ type: "rule" });
      i += 1;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2],
      });
      i += 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      const headers = splitTableRow(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    if (line.startsWith(">")) {
      const quotes: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quotes.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "quote", text: quotes.join(" ") });
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.+)$/);
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      const orderedList = Boolean(ordered);
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i].trim();
        const match = orderedList
          ? current.match(/^\d+\.\s+(.+)$/)
          : current.match(/^[-*]\s+(.+)$/);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push({ type: "list", ordered: orderedList, items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().match(/^(#{1,4})\s+(.+)$/) &&
      !lines[i].trim().match(/^[-*]\s+(.+)$/) &&
      !lines[i].trim().match(/^\d+\.\s+(.+)$/) &&
      !lines[i].trim().startsWith(">") &&
      !isTableStart(lines, i)
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function isTableStart(lines: string[], index: number) {
  return (
    index + 1 < lines.length &&
    lines[index].includes("|") &&
    /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1])
  );
}

function splitTableRow(row: string) {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderInline(text: string) {
  const nodes: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={nodes.length} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        nodes.push(
          <a
            key={nodes.length}
            href={link[2]}
            target="_blank"
            rel="noreferrer"
            className="text-pos underline decoration-pos/40 underline-offset-2"
          >
            {link[1]}
          </a>,
        );
      }
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function stripDecorativeSymbols(value: string) {
  return value
    .replace(/[\u{1F1E6}-\u{1F1FF}\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, "")
    .replace(/[ \t]+$/gm, "")
    .trim();
}

function dedupeUrlKey(url: string) {
  return url.split("#", 1)[0].replace(/\/+$/, "");
}

function MessageArtifacts({ message }: { message: ChatMessage }) {
  const references = dedupeByUrl(message.referenceArticles ?? []);
  // Sources that are already shown as reference articles would otherwise
  // render a second time below, so drop those (and any internal dupes).
  const referencedUrls = new Set(references.map((item) => dedupeUrlKey(item.url)));
  const sources = dedupeByUrl(message.sources ?? []).filter(
    (source) => !referencedUrls.has(dedupeUrlKey(source.url)),
  );

  const steps = message.workflowSteps ?? [];
  const hasSteps = steps.length > 0;
  const hasSources = sources.length > 0;
  const hasReferences = references.length > 0;
  const hasReport = Boolean(message.report);
  if (!hasSources && !hasReferences && !hasReport && !hasSteps) return null;

  return (
    <div className="mt-3 space-y-2 border-t border-hairline pt-3 text-xs">
      {hasSteps && <ActivityTrail steps={steps} />}
      {hasReferences && <ReferenceArticles articles={references} />}
      {hasSources && (
        <div className="space-y-1.5">
          {sources.slice(0, 5).map((source) => (
            <a
              key={source.url}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-start gap-2 rounded-md border border-hairline bg-canvas/40 px-2 py-1.5 text-muted transition hover:text-txt"
            >
              <ExternalLink size={13} className="mt-0.5 shrink-0 text-pos" />
              <span className="min-w-0">
                <span className="block truncate font-medium">
                  {source.title || source.url}
                </span>
                {source.snippet && (
                  <span className="mt-0.5 line-clamp-2 block text-[11px] text-faint">
                    {source.snippet}
                  </span>
                )}
              </span>
            </a>
          ))}
        </div>
      )}
      {message.report && <ReportDownload message={message} />}
    </div>
  );
}

function ActivityTrail({ steps }: { steps: WorkflowStep[] }) {
  if (!steps.length) return null;
  return (
    <details className="rounded-md border border-hairline bg-canvas/40 px-2 py-1.5">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-[11px] font-medium text-muted">
        <Wrench size={12} className="text-faint" />
        {steps.length} step{steps.length === 1 ? "" : "s"} · what the agent did
      </summary>
      <div className="mt-1.5 space-y-1 border-t border-hairline/60 pt-1.5">
        {steps.map((step, i) => (
          <div key={`${step.label}-${i}`} className="flex items-start gap-1.5 text-[11px]">
            <span className={step.status === "error" ? "text-neg" : "text-faint"}>•</span>
            <span className="min-w-0">
              <span className={step.status === "error" ? "font-medium text-neg" : "font-medium text-muted"}>
                {step.label}
              </span>
              {step.detail && <span className="ml-1 text-faint">{step.detail}</span>}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

function dedupeByUrl<T extends { url: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const key = dedupeUrlKey(item.url);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function ReferenceArticles({
  articles: allArticles,
}: {
  articles: ReferenceArticle[];
}) {
  const articles = allArticles.slice(0, 6);
  if (!articles.length) return null;

  return (
    <div className="space-y-1.5 rounded-md border border-pos/20 bg-pos/5 p-2">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-pos">
        <Newspaper size={13} /> Reference articles
      </div>
      {articles.map((article, i) => (
        <a
          key={`${article.url}-${i}`}
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="block rounded-md border border-hairline bg-canvas/50 px-2 py-2 text-muted transition hover:border-pos/40 hover:text-txt"
        >
          <span className="mb-1 flex items-center gap-2">
            <span className="rounded-full border border-pos/30 bg-pos/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-pos">
              {article.kind || "article"}
            </span>
            <span className="truncate text-[11px] text-faint">
              {article.source}
            </span>
          </span>
          <span className="flex items-start gap-2">
            <ExternalLink size={13} className="mt-0.5 shrink-0 text-pos" />
            <span className="min-w-0">
              <span className="block font-medium text-txt">
                {article.title || article.url}
              </span>
              {(article.reason || article.snippet) && (
                <span className="mt-0.5 line-clamp-2 block text-[11px] text-faint">
                  {article.reason || article.snippet}
                </span>
              )}
            </span>
          </span>
        </a>
      ))}
    </div>
  );
}

function ToolActivity({
  compact,
  steps,
}: {
  compact: boolean;
  steps: WorkflowStep[];
}) {
  const width = compact ? "max-w-[92%]" : "max-w-[min(880px,100%)]";
  return (
    <div className={`ml-2 flex justify-start ${width}`}>
      <div className="w-full border-l border-hairline/80 pl-3 text-xs text-muted">
        {steps.length === 0 ? (
          <div className="space-y-1.5">
            <ActivityRow
              icon={<SquareCheck size={12} />}
              label="Read page context"
              detail="Using the current dashboard state"
            />
            <ActivityRow
              icon={<Search size={12} />}
              label="Waiting for tool activity"
              detail="The model will show searches and scraping here as they happen"
              active
            />
          </div>
        ) : (
          <div className="space-y-1.5">
            {steps.map((step, i) => (
              <ActivityRow
                key={`${step.toolName ?? step.label}-${step.detail}-${i}`}
                icon={<Wrench size={12} />}
                label={step.label}
                detail={step.detail}
                error={step.status === "error"}
              />
            ))}
            <ActivityRow
              icon={<Search size={12} />}
              label="Composing answer"
              detail="Using retrieved context to write the response"
              active
            />
          </div>
        )}
      </div>
    </div>
  );
}

function ActivityRow({
  icon,
  label,
  detail,
  active,
  error,
}: {
  icon: React.ReactNode;
  label: string;
  detail: string;
  active?: boolean;
  error?: boolean;
}) {
  return (
    <div className="flex items-start gap-2">
      <span
        className={`mt-0.5 flex h-4 w-7 shrink-0 items-center justify-start ${
          error ? "text-neg" : active ? "text-pos" : "text-faint"
        }`}
      >
        {active ? <TypingDots /> : icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className={error ? "font-medium text-neg" : "font-medium text-muted"}>
          {label}
        </span>
        <span className="ml-1 text-[11px] leading-snug text-faint">
          {detail}
        </span>
      </span>
    </div>
  );
}

function ReportDownload({ message }: { message: ChatMessage }) {
  const report = message.report;
  const [open, setOpen] = useState(false);
  if (!report) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-2 rounded-md border border-pos/30 bg-pos/10 px-2 py-2 text-left text-pos transition hover:bg-pos/15"
      >
        <FileText size={14} />
        <span className="min-w-0 flex-1 truncate">{report.title}</span>
        <Eye size={14} />
      </button>
      {open && <ReportModal report={report} onClose={() => setOpen(false)} />}
    </>
  );
}

function ReportModal({
  report,
  onClose,
}: {
  report: ReportArtifact;
  onClose: () => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const html = useMemo(() => buildReportHtml(report), [report]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const downloadPdf = () => {
    const frameWindow = iframeRef.current?.contentWindow;
    if (!frameWindow) return;
    // Print just the preview frame, letting the user "Save as PDF".
    frameWindow.focus();
    frameWindow.print();
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-[min(820px,100%)] flex-col overflow-hidden rounded-2xl border border-hairline bg-canvas shadow-float"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{report.title}</p>
            <p className="text-[11px] text-muted">Report preview</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={downloadPdf}
              className="flex items-center gap-1.5 rounded-lg bg-pos px-3 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105"
            >
              <Download size={14} /> Download PDF
            </button>
            <button
              onClick={onClose}
              className="rounded-md p-1.5 text-muted transition hover:bg-raised hover:text-txt"
              aria-label="Close preview"
            >
              <X size={16} />
            </button>
          </div>
        </header>
        <iframe
          ref={iframeRef}
          title={report.title}
          srcDoc={html}
          className="min-h-0 w-full flex-1 bg-white"
        />
      </div>
    </div>,
    document.body,
  );
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(value: string) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

function renderInlineHtml(text: string) {
  const pattern = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let out = "";
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      out += escapeHtml(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      out += `<strong>${escapeHtml(token.slice(2, -2))}</strong>`;
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        out += `<a href="${escapeAttr(link[2])}">${escapeHtml(link[1])}</a>`;
      }
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    out += escapeHtml(text.slice(lastIndex));
  }
  return out;
}

function blockToHtml(block: MarkdownBlock): string {
  if (block.type === "heading") {
    const level = Math.min(block.level + 1, 6);
    return `<h${level}>${renderInlineHtml(block.text)}</h${level}>`;
  }
  if (block.type === "quote") {
    return `<blockquote>${renderInlineHtml(block.text)}</blockquote>`;
  }
  if (block.type === "list") {
    const tag = block.ordered ? "ol" : "ul";
    const items = block.items
      .map((item) => `<li>${renderInlineHtml(item)}</li>`)
      .join("");
    return `<${tag}>${items}</${tag}>`;
  }
  if (block.type === "table") {
    const head = block.headers
      .map((header) => `<th>${renderInlineHtml(header)}</th>`)
      .join("");
    const rows = block.rows
      .map(
        (row) =>
          `<tr>${block.headers
            .map((_, i) => `<td>${renderInlineHtml(row[i] ?? "")}</td>`)
            .join("")}</tr>`,
      )
      .join("");
    return `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  }
  if (block.type === "rule") {
    return "<hr />";
  }
  if (block.type === "code") {
    return `<pre><code>${escapeHtml(block.text)}</code></pre>`;
  }
  return `<p>${renderInlineHtml(block.text)}</p>`;
}

function formatReportDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "long",
    timeStyle: "short",
  }).format(date);
}

function buildReportHtml(report: ReportArtifact) {
  const blocks = parseMarkdown(stripDecorativeSymbols(report.markdown));
  const body = blocks.map(blockToHtml).join("\n");
  const title = escapeHtml(report.title);
  const generated = formatReportDate(report.generatedAt);
  const meta = generated ? `Generated ${escapeHtml(generated)}` : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${title}</title>
<style>
  *, *::before, *::after {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a1d1a; margin: 0; padding: 48px 56px; line-height: 1.55; font-size: 12.5px;
  }
  .report-head { border-bottom: 2px solid #16a34a; padding-bottom: 16px; margin-bottom: 28px; }
  .brand { font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #16a34a; font-weight: 700; }
  .report-head h1 { font-size: 24px; line-height: 1.25; margin: 10px 0 6px; }
  .meta { font-size: 11px; color: #6b7280; }
  h2 { font-size: 16px; margin: 24px 0 8px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
  h3, h4, h5, h6 { font-size: 13.5px; margin: 16px 0 6px; }
  p { margin: 0 0 10px; }
  ul, ol { margin: 0 0 12px; padding-left: 22px; }
  li { margin: 3px 0; }
  blockquote { border-left: 3px solid #16a34a; margin: 0 0 12px; padding: 4px 0 4px 14px; color: #4b5563; }
  table { border-collapse: collapse; width: 100%; margin: 0 0 14px; font-size: 11.5px; }
  th, td { border: 1px solid #d1d5db; padding: 6px 9px; text-align: left; vertical-align: top; }
  th { background: #f0fdf4; }
  a { color: #15803d; text-decoration: none; word-break: break-word; }
  pre { background: #f6f7f6; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; overflow-x: auto; font-size: 11px; }
  hr { border: none; border-top: 1px solid #e5e7eb; margin: 18px 0; }
  @page { margin: 16mm 0; }
  @media print {
    html, body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    /* Keep the same side padding as the on-screen preview; @page handles
       top/bottom. Horizontal padding on body stays consistent on every page
       even when the printer ignores @page side margins. */
    body { padding: 0 56px; }
  }
</style>
</head>
<body>
  <header class="report-head">
    <div class="brand">PolyFintech ESG Intelligence</div>
    <h1>${title}</h1>
    ${meta ? `<div class="meta">${meta}</div>` : ""}
  </header>
  <main>${body}</main>
</body>
</html>`;
}

function TypingDots() {
  return (
    <span className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-faint"
          style={{
            animation: "fade-up 0.9s ease-in-out infinite alternate",
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </span>
  );
}
