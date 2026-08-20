export type FeedbackStatus = "open" | "reviewing" | "resolved" | "dismissed";

export type FeedbackRecord = {
  id: string;
  sessionId: string | null;
  messageId: string | null;
  createdAt: string;
  rating: string;
  reason: string;
  reasonLabel: string;
  comment: string;
  responseText: string;
  promptText: string;
  model: string | null;
  surface: string | null;
  artifacts: {
    sources?: Array<{ title: string; url: string; source?: string }>;
    toolResults?: Array<{ name: string; status: string; summary: string }>;
    workflowSteps?: Array<{ label: string; status: string; detail: string }>;
  };
  pageContext: Record<string, unknown>;
  status: FeedbackStatus;
  reviewer: string | null;
  reviewerNote: string;
  correctedResponse: string;
  reviewedAt: string | null;
};

export type FeedbackStats = {
  total: number;
  byStatus: Partial<Record<FeedbackStatus, number>>;
  byReason: Record<string, number>;
  reasonLabels: Record<string, string>;
  trainablePairs: number;
  latestAt: string | null;
};

/** Kept in sync with REASONS in backend/app/feedback.py. */
export const FEEDBACK_REASONS: Array<{ id: string; label: string }> = [
  { id: "inaccurate", label: "Factually wrong" },
  { id: "unsupported", label: "Not supported by the cited sources" },
  { id: "fabricated", label: "Fabricated source or number" },
  { id: "incomplete", label: "Missed part of the question" },
  { id: "off_topic", label: "Did not answer the question" },
  { id: "tone", label: "Tone or formatting problem" },
  { id: "unsafe", label: "Unsafe or inappropriate" },
  { id: "other", label: "Other" },
];

export const STATUS_LABELS: Record<FeedbackStatus, string> = {
  open: "Open",
  reviewing: "In review",
  resolved: "Resolved",
  dismissed: "Dismissed",
};

export async function submitFeedback(payload: {
  sessionId?: string | null;
  messageId?: string | null;
  reason: string;
  comment: string;
  responseText: string;
  promptText: string;
  model?: string | null;
  surface?: string;
  artifacts?: Record<string, unknown>;
  pageContext?: Record<string, unknown>;
}): Promise<FeedbackRecord> {
  const response = await fetch("/api/assistant/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating: "flag", ...payload }),
  });
  if (!response.ok) {
    throw new Error(`Could not submit feedback (${response.status})`);
  }
  return (await response.json()) as FeedbackRecord;
}

export async function listFeedback(
  status: FeedbackStatus | "all" = "all",
): Promise<FeedbackRecord[]> {
  const query = status === "all" ? "" : `?status=${status}`;
  const response = await fetch(`/api/assistant/feedback${query}`);
  if (!response.ok) {
    throw new Error(`Could not load flagged responses (${response.status})`);
  }
  return (await response.json()) as FeedbackRecord[];
}

export async function loadFeedbackStats(): Promise<FeedbackStats> {
  const response = await fetch("/api/assistant/feedback/stats");
  if (!response.ok) {
    throw new Error(`Could not load feedback stats (${response.status})`);
  }
  return (await response.json()) as FeedbackStats;
}

export async function reviewFeedback(
  id: string,
  payload: {
    status?: FeedbackStatus;
    reviewerNote?: string;
    correctedResponse?: string;
    reviewer?: string;
  },
): Promise<FeedbackRecord> {
  const response = await fetch(`/api/assistant/feedback/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Could not update the review (${response.status})`);
  }
  return (await response.json()) as FeedbackRecord;
}

export async function deleteFeedback(id: string): Promise<void> {
  const response = await fetch(`/api/assistant/feedback/${id}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Could not delete the flag (${response.status})`);
  }
}

/** Downloads the RLHF export. `all` includes rows that have no human correction
 *  yet — those carry no preference pair, only the rejected side. */
export async function downloadFeedbackExport(all: boolean): Promise<void> {
  const response = await fetch(
    `/api/assistant/feedback/export${all ? "?all=true" : ""}`,
  );
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "rlhf-feedback.jsonl";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
