import { useState } from "react";
import { Sparkles, Trash2 } from "lucide-react";
import ChatThread from "./ChatThread";
import { useChat, type ChatSessionSummary } from "./useChat";

export default function ChatPage() {
  const {
    sessions,
    activeSessionId,
    createSession,
    selectSession,
    deleteSession,
    pending,
  } = useChat();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDeleteSession = async (sessionId: string) => {
    setDeleteError(null);
    try {
      await deleteSession(sessionId);
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : "Failed to delete chat.",
      );
    }
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col px-6 py-6 sm:px-10 lg:px-12">
      <header className="pb-5">
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
      <div className="grid min-h-0 flex-1 gap-4 pb-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <SessionHistoryPanel
          sessions={sessions}
          activeSessionId={activeSessionId}
          pending={pending}
          onCreateSession={createSession}
          onSelectSession={selectSession}
          onDeleteSession={handleDeleteSession}
          deleteError={deleteError}
        />
        <div className="min-h-0 rounded-2xl border border-hairline bg-canvas/40 p-3 shadow-panel">
          <ChatThread />
        </div>
      </div>
    </div>
  );
}

function SessionHistoryPanel({
  sessions,
  activeSessionId,
  pending,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  deleteError,
}: {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  pending: boolean;
  onCreateSession: () => Promise<void>;
  onSelectSession: (sessionId: string) => Promise<void>;
  onDeleteSession: (sessionId: string) => Promise<void>;
  deleteError: string | null;
}) {
  return (
    <aside className="min-h-0 rounded-2xl border border-hairline bg-surface p-3 shadow-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Chat history
          </p>
          <p className="text-sm text-muted">{sessions.length} sessions</p>
        </div>
        <button
          onClick={() => void onCreateSession()}
          disabled={pending}
          className="rounded-lg bg-pos px-3 py-1.5 text-xs font-semibold text-canvas transition hover:brightness-105 disabled:opacity-40"
        >
          New
        </button>
      </div>

      {deleteError && (
        <p className="mt-3 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-[11px] text-neg">
          {deleteError}
        </p>
      )}

      <div className="mt-3 max-h-[calc(100vh-14rem)] space-y-1.5 overflow-y-auto pr-1">
        {sessions.map((session) => {
          const active = session.id === activeSessionId;
          return (
            <div
              key={session.id}
              className={`group relative rounded-xl border transition ${
                active
                  ? "border-pos bg-pos/10 text-txt"
                  : "border-transparent bg-canvas/45 text-muted hover:border-hairline hover:bg-raised hover:text-txt"
              }`}
            >
              <button
                onClick={() => void onSelectSession(session.id)}
                disabled={pending}
                className="w-full rounded-xl px-3 py-2.5 pr-9 text-left disabled:opacity-60"
              >
                <span className="block truncate text-sm font-semibold">
                  {session.title}
                </span>
                <span className="mt-1 flex items-center justify-between gap-2 text-[11px] text-faint">
                  <span>{formatSessionDate(session.updatedAt)}</span>
                  <span>{session.messageCount} msgs</span>
                </span>
              </button>
              <button
                onClick={() => {
                  if (
                    window.confirm(`Delete chat "${session.title}"?`)
                  ) {
                    void onDeleteSession(session.id);
                  }
                }}
                disabled={pending}
                className="absolute right-2 top-2 rounded-md p-1.5 text-faint opacity-0 transition hover:bg-neg/10 hover:text-neg focus:opacity-100 group-hover:opacity-100 disabled:opacity-30"
                aria-label={`Delete chat "${session.title}"`}
                title="Delete chat"
              >
                <Trash2 size={14} />
              </button>
            </div>
          );
        })}
        {sessions.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline p-3 text-sm text-muted">
            No saved chats yet.
          </div>
        )}
      </div>
    </aside>
  );
}

function formatSessionDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Just now";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
