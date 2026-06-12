import { Sparkles } from "lucide-react";
import ChatThread from "./ChatThread";

export default function ChatPage() {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-5 py-6 sm:px-8">
      <header className="pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-pos/15 text-pos">
            <Sparkles size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold">AI Assistant</h1>
            <p className="text-sm text-muted">
              Conversational ESG research across the full universe
            </p>
          </div>
        </div>
      </header>
      <div className="min-h-0 flex-1 pb-4">
        <ChatThread />
      </div>
    </div>
  );
}
