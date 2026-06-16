import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { AssistantPageContext } from "./PageContext";

export type ChatRole = "user" | "assistant";

export type ChatSource = {
  title: string;
  url: string;
  snippet?: string | null;
  source: string;
};

export type ReferenceArticle = {
  title: string;
  url: string;
  snippet?: string | null;
  source: string;
  kind: string;
  reason?: string | null;
};

export type ToolResult = {
  name: string;
  status: "ok" | "error";
  summary: string;
  sourceCount: number;
};

export type WorkflowStep = {
  label: string;
  status: "ok" | "error" | "running";
  detail: string;
  toolName?: string | null;
};

export type ReportArtifact = {
  title: string;
  markdown: string;
  generatedAt: string;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  sources?: ChatSource[];
  referenceArticles?: ReferenceArticle[];
  toolResults?: ToolResult[];
  workflowSteps?: WorkflowStep[];
  report?: ReportArtifact | null;
  model?: string;
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};

export type ChatSurface = "page" | "floating";

type ConversationApi = {
  messages: ChatMessage[];
  activeSessionId: string | null;
  pending: boolean;
  activeWorkflowSteps: WorkflowStep[];
  createSession: () => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  send: (raw: string, pageContext: AssistantPageContext) => Promise<void>;
  stop: () => void;
  startNewChat: () => void;
};

type ChatContextValue = {
  sessions: ChatSessionSummary[];
  page: ConversationApi;
  floating: ConversationApi;
  deleteSession: (sessionId: string) => Promise<void>;
  refreshSessions: () => Promise<ChatSessionSummary[]>;
};

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "I'm your ESG research agent. I can use the dashboard context, scrape public web pages, and produce source-backed reports.",
};

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);

  const upsertSession = useCallback((session: ChatSessionSummary) => {
    setSessions((current) => {
      const without = current.filter((item) => item.id !== session.id);
      return [session, ...without].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      );
    });
  }, []);

  const loadSessions = useCallback(async () => {
    const response = await fetch("/api/assistant/sessions");
    if (!response.ok) {
      throw new Error(`Failed to load chat sessions (${response.status})`);
    }
    const data: ChatSessionSummary[] = await response.json();
    setSessions(data);
    return data;
  }, []);

  // The full-page assistant continues the most recent saved chat.
  const page = useConversation("page", {
    autoload: true,
    loadSessions,
    upsertSession,
  });
  // The floating copilot always starts a fresh chat scoped to the current
  // page, but persists to the same session store so it shows up in the
  // full-page chat history.
  const floating = useConversation("floating", {
    autoload: false,
    loadSessions,
    upsertSession,
  });

  const deleteSession = useCallback(
    async (sessionId: string) => {
      const response = await fetch(`/api/assistant/sessions/${sessionId}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 404) {
        throw new Error(`Failed to delete chat session (${response.status})`);
      }
      setSessions((current) => current.filter((item) => item.id !== sessionId));
      if (page.activeSessionId === sessionId) page.startNewChat();
      if (floating.activeSessionId === sessionId) floating.startNewChat();
    },
    [page, floating],
  );

  const value = useMemo(
    () => ({ sessions, page, floating, deleteSession, refreshSessions: loadSessions }),
    [sessions, page, floating, deleteSession, loadSessions],
  );

  return createElement(ChatContext.Provider, { value }, children);
}

function useConversation(
  surface: ChatSurface,
  opts: {
    autoload: boolean;
    loadSessions: () => Promise<ChatSessionSummary[]>;
    upsertSession: (session: ChatSessionSummary) => void;
  },
): ConversationApi {
  const { autoload, loadSessions, upsertSession } = opts;
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [activeWorkflowSteps, setActiveWorkflowSteps] = useState<WorkflowStep[]>(
    [],
  );
  const counter = useRef(0);
  const messagesRef = useRef<ChatMessage[]>([WELCOME]);
  const initialized = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const nextId = () => {
    counter.current += 1;
    return `${surface}-m${counter.current}`;
  };

  const commitMessages = (next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  };

  const loadSession = useCallback(
    async (sessionId: string) => {
      const response = await fetch(`/api/assistant/sessions/${sessionId}`);
      if (!response.ok) {
        throw new Error(`Failed to load chat session (${response.status})`);
      }
      const data = await response.json();
      setActiveSessionId(data.session.id);
      upsertSession(data.session);
      commitMessages(withWelcome(data.messages ?? []));
    },
    [upsertSession],
  );

  const createSession = useCallback(async () => {
    if (pending) return;
    const session = await createSessionRemote();
    upsertSession(session);
    setActiveSessionId(session.id);
    commitMessages([WELCOME]);
  }, [pending, upsertSession]);

  const selectSession = useCallback(
    async (sessionId: string) => {
      if (pending || sessionId === activeSessionId) return;
      try {
        await loadSession(sessionId);
      } catch {
        // The session was likely deleted elsewhere (stale list) — re-sync from
        // the backend so the dead row disappears instead of silently failing.
        try {
          await loadSessions();
        } catch {
          /* ignore */
        }
      }
    },
    [activeSessionId, loadSession, loadSessions, pending],
  );

  // Drop the active session and reset to an empty chat without touching the
  // backend. Used by the floating copilot so each open starts fresh.
  const startNewChat = useCallback(() => {
    if (pending) return;
    setActiveSessionId(null);
    setActiveWorkflowSteps([]);
    commitMessages([WELCOME]);
  }, [pending]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!autoload) return;
    let cancelled = false;

    async function initialize() {
      try {
        const loadedSessions = await loadSessions();
        if (cancelled) return;
        if (loadedSessions.length > 0) {
          await loadSession(loadedSessions[0].id);
          return;
        }
        setActiveSessionId(null);
        commitMessages([WELCOME]);
      } catch {
        if (!cancelled) {
          commitMessages([WELCOME]);
        }
      }
    }

    void initialize();
    return () => {
      cancelled = true;
    };
  }, [autoload, loadSession, loadSessions]);

  const send = useCallback(
    async (raw: string, pageContext: AssistantPageContext) => {
      const content = raw.trim();
      if (!content || pending) return;
      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await createSessionRemote();
        sessionId = session.id;
        upsertSession(session);
        setActiveSessionId(session.id);
      }

      const userMessage: ChatMessage = {
        id: nextId(),
        role: "user",
        content,
      };
      const requestMessages = [
        ...persistedMessages(messagesRef.current),
        userMessage,
      ];
      commitMessages(withWelcome(requestMessages));
      setPending(true);
      setActiveWorkflowSteps([]);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch("/api/assistant/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: requestMessages.map(({ role, content }) => ({
              role,
              content,
            })),
            pageContext,
            sessionId,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Assistant request failed (${response.status})`);
        }
        if (!response.body) {
          throw new Error("Assistant stream did not return a readable body.");
        }

        const data = await readAssistantStream(response, (step) => {
          setActiveWorkflowSteps((prev) => [...prev, step]);
        });
        if (data.session) {
          upsertSession(data.session);
        } else {
          void loadSessions();
        }
        const assistantMessage: ChatMessage = {
          id: nextId(),
          role: "assistant",
          content: data.response.message?.content ?? "No response returned.",
          sources: data.response.sources ?? [],
          referenceArticles: data.response.referenceArticles ?? [],
          toolResults: data.response.toolResults ?? [],
          workflowSteps: data.response.workflowSteps ?? [],
          report: data.response.report ?? null,
        };
        commitMessages(withWelcome([...requestMessages, assistantMessage]));
      } catch (error) {
        if (
          controller.signal.aborted ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          const stoppedMessage: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content: "Generation stopped.",
          };
          commitMessages(withWelcome([...requestMessages, stoppedMessage]));
        } else {
          const assistantMessage: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content:
              error instanceof Error
                ? error.message
                : "The assistant request failed.",
            toolResults: [
              {
                name: "assistant",
                status: "error",
                summary: "Backend request failed.",
                sourceCount: 0,
              },
            ],
          };
          commitMessages(withWelcome([...requestMessages, assistantMessage]));
        }
      } finally {
        abortRef.current = null;
        setPending(false);
        setActiveWorkflowSteps([]);
      }
    },
    [activeSessionId, loadSessions, pending, upsertSession],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return useMemo(
    () => ({
      messages,
      activeSessionId,
      pending,
      activeWorkflowSteps,
      createSession,
      selectSession,
      send,
      stop,
      startNewChat,
    }),
    [
      messages,
      activeSessionId,
      pending,
      activeWorkflowSteps,
      createSession,
      selectSession,
      send,
      stop,
      startNewChat,
    ],
  );
}

export function useChat(surface: ChatSurface = "page") {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error("useChat must be used within ChatProvider");
  }
  const conversation = surface === "floating" ? ctx.floating : ctx.page;
  return {
    ...conversation,
    sessions: ctx.sessions,
    deleteSession: ctx.deleteSession,
    refreshSessions: ctx.refreshSessions,
  };
}

async function createSessionRemote() {
  const response = await fetch("/api/assistant/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New ESG chat" }),
  });
  if (!response.ok) {
    throw new Error(`Failed to create chat session (${response.status})`);
  }
  return (await response.json()) as ChatSessionSummary;
}

function withWelcome(messages: ChatMessage[]) {
  return [WELCOME, ...messages.filter((message) => message.id !== WELCOME.id)];
}

function persistedMessages(messages: ChatMessage[]) {
  return messages.filter((message) => message.id !== WELCOME.id);
}

async function readAssistantStream(
  response: Response,
  onWorkflowStep: (step: WorkflowStep) => void,
) {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Assistant stream could not be read.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload: any = null;
  let finalSession: ChatSessionSummary | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const event = parseStreamEvent(line);
      if (!event) continue;
      if (event.type === "workflow" && event.step) {
        onWorkflowStep(event.step);
      }
      if (event.type === "final" && event.response) {
        finalPayload = event.response;
        finalSession = event.session ?? null;
      }
      if (event.type === "error") {
        throw new Error(event.message ?? "Assistant stream failed.");
      }
    }
  }

  if (buffer.trim()) {
    const event = parseStreamEvent(buffer);
    if (event?.type === "workflow" && event.step) {
      onWorkflowStep(event.step);
    }
    if (event?.type === "final" && event.response) {
      finalPayload = event.response;
      finalSession = event.session ?? null;
    }
    if (event?.type === "error") {
      throw new Error(event.message ?? "Assistant stream failed.");
    }
  }

  if (!finalPayload) {
    throw new Error("Assistant stream ended without a final response.");
  }
  return { response: finalPayload, session: finalSession };
}

function parseStreamEvent(line: string) {
  const trimmed = line.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

// Page-scoped prompts for the floating copilot, which always has a concrete
// page (company/sector) in context.
export const CONTEXT_SUGGESTIONS = [
  "Summarize what I am looking at",
  "Explain this ESG score with sources",
  "Find recent ESG news for this view",
  "Scrape this company's website",
  "Generate a report from this page",
];

// Universe-wide prompts for the full-page assistant, which has no single
// page in view.
export const UNIVERSE_SUGGESTIONS = [
  "Compare two companies' ESG scores",
  "Which companies lead ESG in a sector?",
  "How are ESG scores calculated?",
  "Summarize recent ESG regulation",
  "Generate an ESG report on a company",
];

export function suggestionsForSurface(surface: ChatSurface) {
  return surface === "floating" ? CONTEXT_SUGGESTIONS : UNIVERSE_SUGGESTIONS;
}
