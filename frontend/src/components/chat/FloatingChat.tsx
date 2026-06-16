import { useState } from "react";
import { MessageSquareText, X } from "lucide-react";
import ChatThread from "./ChatThread";
import { useChat } from "./useChat";

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const { startNewChat } = useChat("floating");

  const openChat = () => {
    // Each time the copilot is opened it begins a fresh, page-scoped chat
    // instead of resuming whatever was last discussed.
    startNewChat();
    setOpen(true);
  };

  return (
    <>
      <div
        className={`fixed bottom-5 right-5 z-40 w-[min(420px,calc(100vw-2.5rem))] origin-bottom-right transition-all duration-300 ${
          open
            ? "scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0"
        }`}
      >
        <div className="flex h-[min(560px,75vh)] flex-col rounded-2xl border border-hairline bg-canvas shadow-float">
          <header className="flex items-center justify-between border-b border-hairline px-4 py-3">
            <div className="flex items-center gap-2">
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
            <ChatThread compact surface="floating" />
          </div>
        </div>
      </div>

      {!open && (
        <button
          onClick={openChat}
          className="fixed bottom-5 right-5 z-30 flex h-12 w-12 items-center justify-center rounded-full bg-pos text-canvas shadow-float transition hover:brightness-110"
          aria-label="Open AI agent"
        >
          <MessageSquareText size={20} />
        </button>
      )}
    </>
  );
}
