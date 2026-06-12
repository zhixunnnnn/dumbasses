import { useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";
import {
  SUGGESTIONS,
  useChat,
  type ChatMessage,
} from "./useChat";

type Props = {
  compact?: boolean;
};

export default function ChatThread({ compact = false }: Props) {
  const { messages, pending, send } = useChat();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  const submit = () => {
    send(draft);
    setDraft("");
  };

  const showSuggestions = messages.length <= 1;

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-1 py-2">
        {messages.map((m) => (
          <Bubble key={m.id} message={m} compact={compact} />
        ))}
        {pending && (
          <div className="flex items-center gap-2 px-1 text-sm text-faint">
            <Sparkles size={14} className="text-pos" />
            <TypingDots />
          </div>
        )}
        {showSuggestions && (
          <div className="flex flex-wrap gap-2 px-1 pt-1">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
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
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Ask about any company, sector, or signal…"
          className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-faint"
        />
        <button
          onClick={submit}
          disabled={!draft.trim()}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-pos text-canvas transition disabled:opacity-30"
          aria-label="Send"
        >
          <ArrowUp size={16} />
        </button>
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
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`${compact ? "max-w-[85%]" : "max-w-[80%]"} rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-raised text-txt"
            : "border border-hairline bg-surface text-txt"
        }`}
      >
        {!isUser && (
          <span className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-pos">
            <Sparkles size={12} /> Copilot
          </span>
        )}
        {message.content}
      </div>
    </div>
  );
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
