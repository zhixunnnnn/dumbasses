/** Reviewer-pinned fact overrides.
 *
 *  A flagged answer that is wrong about one number gets fixed here rather than
 *  by retrieving a similar past correction: the value is patched into the ESG
 *  payload before the agent sees it, so there is nothing for the model to
 *  ignore. Mirrors backend/app/fact_overrides.py. */

export type OverrideField = {
  field: string;
  label: string;
  kind: "number" | "text";
  min: number | null;
  max: number | null;
  hint: string;
};

export type OverrideRecord = {
  id: string;
  companyId: string;
  field: string;
  fieldLabel: string;
  value: number | string;
  note: string;
  sourceUrl: string;
  feedbackId: string | null;
  reviewer: string | null;
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
  isExpired: boolean;
};

export type OverrideStats = {
  total: number;
  active: number;
  expired: number;
  companies: number;
  fromFeedback: number;
};

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function loadOverrideFields(): Promise<OverrideField[]> {
  const response = await fetch("/api/assistant/overrides/fields");
  if (!response.ok) {
    throw new Error(`Could not load overridable fields (${response.status})`);
  }
  return (await response.json()) as OverrideField[];
}

export async function listOverrides(
  company?: string,
): Promise<OverrideRecord[]> {
  const query = company ? `?company=${encodeURIComponent(company)}` : "";
  const response = await fetch(`/api/assistant/overrides${query}`);
  if (!response.ok) {
    throw new Error(`Could not load fact overrides (${response.status})`);
  }
  return (await response.json()) as OverrideRecord[];
}

export async function loadOverrideStats(): Promise<OverrideStats> {
  const response = await fetch("/api/assistant/overrides/stats");
  if (!response.ok) {
    throw new Error(`Could not load override stats (${response.status})`);
  }
  return (await response.json()) as OverrideStats;
}

/** Upserts by (companyId, field): re-pinning a field replaces its value rather
 *  than stacking a second, ambiguous override. */
export async function saveOverride(payload: {
  companyId: string;
  field: string;
  value: number | string;
  note?: string;
  sourceUrl?: string;
  feedbackId?: string | null;
  reviewer?: string | null;
  expiresAt?: string | null;
}): Promise<OverrideRecord> {
  const response = await fetch("/api/assistant/overrides", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      await readError(response, `Could not pin the value (${response.status})`),
    );
  }
  return (await response.json()) as OverrideRecord;
}

export async function deleteOverride(id: string): Promise<void> {
  const response = await fetch(`/api/assistant/overrides/${id}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Could not remove the override (${response.status})`);
  }
}
