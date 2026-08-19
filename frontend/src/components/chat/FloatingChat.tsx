import { useEffect, useMemo, useRef, useState } from "react";
import { MessageSquareText, X } from "lucide-react";
import ChatThread from "./ChatThread";
import { useChat } from "./useChat";
import { useAssistantPageContext } from "./PageContext";

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const { startNewChat } = useChat("floating");
  const pageContext = useAssistantPageContext();
  const contextKey = useMemo(() => JSON.stringify({
    route: pageContext.route,
    companyId: (pageContext.company as { company_id?: string; id?: string } | undefined)?.company_id
      ?? (pageContext.company as { company_id?: string; id?: string } | undefined)?.id
      ?? pageContext.companyId,
    title: pageContext.title,
  }), [pageContext]);
  const activeContextKey = useRef<string | null>(null);

  useEffect(() => {
    if (!open || activeContextKey.current === null || activeContextKey.current === contextKey) return;
    startNewChat();
    activeContextKey.current = contextKey;
  }, [contextKey, open, startNewChat]);

  const openChat = () => {
    if (activeContextKey.current !== contextKey) {
      startNewChat();
      activeContextKey.current = contextKey;
    }
    setOpen(true);
  };

  return (
    <>
      <div
        className={`fixed inset-x-2 bottom-2 z-40 origin-bottom-right transition-all duration-300 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:w-[min(420px,calc(100vw-2.5rem))] ${
          open
            ? "scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0"
        }`}
      >
        <div className="flex h-[min(680px,calc(100dvh-5.5rem))] flex-col rounded-2xl border border-hairline bg-canvas shadow-float sm:h-[min(560px,75vh)]">
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
          className="safe-float fixed bottom-4 right-4 z-30 flex h-12 w-12 items-center justify-center rounded-full bg-pos text-canvas shadow-float transition hover:brightness-110 sm:bottom-5 sm:right-5"
          aria-label="Open AI agent"
        >
          <MessageSquareText size={20} />
        </button>
      )}
    </>
  );
}
