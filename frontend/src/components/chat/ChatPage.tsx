import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import ChatThread from "./ChatThread";
import { useChat, type ChatSessionSummary } from "./useChat";

export default function ChatPage() {
  const {
    sessions,
    activeSessionId,
    createSession,
    selectSession,
    deleteSession,
    refreshSessions,
    pending,
  } = useChat();
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Re-sync the session list whenever the chat page opens, so rows can't go
  // stale (deleted-elsewhere entries that 404 on click).
  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

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
      <header className="mb-5 border-b border-hairline pb-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-faint">
              ESG Intelligence
            </p>
            <h1 className="mt-1.5 text-[22px] font-semibold leading-none tracking-tight text-txt">
              AI Agent
            </h1>
            <p className="mt-2 text-[13px] leading-snug text-muted">
              Conversational ESG research across the full universe
            </p>
          </div>
          <div className="mt-0.5 hidden shrink-0 items-center gap-1.5 sm:flex">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-pos/60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-pos" />
            </span>
            <span className="text-[11px] font-medium tracking-wide text-muted">Live</span>
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
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
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
              {confirmingId === session.id ? (
                <div className="absolute right-1.5 top-1.5 flex items-center gap-1">
                  <button
                    onClick={() => {
                      setConfirmingId(null);
                      void onDeleteSession(session.id);
                    }}
                    className="rounded-md bg-neg px-2 py-1 text-[10px] font-semibold text-canvas transition hover:brightness-110"
                    title="Confirm delete"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setConfirmingId(null)}
                    className="rounded-md border border-hairline bg-surface px-2 py-1 text-[10px] font-medium text-muted transition hover:text-txt"
                    title="Cancel"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmingId(session.id)}
                  className="absolute right-2 top-2 rounded-md p-1.5 text-faint opacity-0 transition hover:bg-neg/10 hover:text-neg focus:opacity-100 group-hover:opacity-100"
                  aria-label={`Delete chat "${session.title}"`}
                  title="Delete chat"
                >
                  <Trash2 size={14} />
                </button>
              )}
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
