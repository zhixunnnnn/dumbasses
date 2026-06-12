import { useState } from "react";
import { MessageSquareText, X, Sparkles } from "lucide-react";
import ChatThread from "./ChatThread";

export default function FloatingChat() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div
        className={`fixed bottom-5 right-5 z-40 w-[min(380px,calc(100vw-2.5rem))] origin-bottom-right transition-all duration-300 ${
          open
            ? "scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0"
        }`}
      >
        <div className="flex h-[min(560px,75vh)] flex-col rounded-2xl border border-hairline bg-canvas shadow-float">
          <header className="flex items-center justify-between border-b border-hairline px-4 py-3">
            <div className="flex items-center gap-2">
              <Sparkles size={15} className="text-pos" />
              <span className="text-sm font-semibold">ESG Copilot</span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-muted transition hover:bg-raised hover:text-txt"
              aria-label="Close chat"
            >
              <X size={16} />
            </button>
          </header>
          <div className="min-h-0 flex-1 px-3 py-2">
            <ChatThread compact />
          </div>
        </div>
      </div>

      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-5 right-5 z-30 flex h-12 w-12 items-center justify-center rounded-full bg-pos text-canvas shadow-float transition hover:brightness-110"
        aria-label="Open AI assistant"
      >
        {open ? <X size={20} /> : <MessageSquareText size={20} />}
      </button>
    </>
  );
}
