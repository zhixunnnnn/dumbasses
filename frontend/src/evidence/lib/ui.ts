import type { Provenance, QuadrantKey, RegQuality, VerifyState } from "../types";

export const QUADRANT: Record<
  QuadrantKey,
  { label: string; color: string; blurb: string; emoji: string }
> = {
  HIDDEN_WINNERS: {
    label: "Hidden Winners",
    color: "#3ecf8e",
    blurb: "Rated low but cutting emissions — a decarbonisation the score hasn't caught up to.",
    emoji: "🚀",
  },
  FUTURE_LEADERS: {
    label: "Future Leaders",
    color: "#4cc4d4",
    blurb: "Rated well AND emissions falling — genuine, evidenced ESG quality.",
    emoji: "🌟",
  },
  VALUE_TRAPS: {
    label: "Value Traps",
    color: "#e0b24a",
    blurb: "Rated low and emissions rising — structural transition risk.",
    emoji: "⚠️",
  },
  OVERRATED: {
    label: "Overrated Leaders",
    color: "#ec6a5e",
    blurb: "Rated well but emissions rising — the rating flatters a worsening carbon path.",
    emoji: "🧱",
  },
};

export const STATE_COLOR: Record<VerifyState, string> = {
  VERIFIED: "#3ecf8e",
  ASSERTED: "#e0b24a",
  INFERRED: "#a78bfa",
  ABSENT: "#6a665f",
};

export const REG_COLOR: Record<RegQuality, string> = {
  MET: "#3ecf8e",
  PARTIAL: "#e0b24a",
  MISSING: "#ec6a5e",
  NA: "#6a665f",
};

export const PILLAR_COLOR: Record<string, string> = {
  E: "#3ecf8e",
  S: "#4cc4d4",
  G: "#a78bfa",
};

export const na = (v: number | null | undefined, dp = 1, suffix = ""): string =>
  v === null || v === undefined ? "N.A." : `${v.toFixed(dp)}${suffix}`;

// Why a number is N.A. when it genuinely cannot be computed (no data at all), as opposed
// to being computed from illustrative inputs — that case is labelled, not blanked.
export const NA_REASON = {
  raters: "no rater covers this company",
  percentile: "needs 5 comparable companies",
  benchmark: "no scored company in this industry",
  gap: "needs a consensus and an evidence percentile",
  momentum: "needs 3 years of evidence",
} as const;

// Provenance badges. A viewer must never have to guess whether a number was measured.
export const PROVENANCE: Record<Provenance, { label: string; color: string; hint: string }> = {
  real: {
    label: "real",
    color: "#3ecf8e",
    hint: "Computed only from real, sourced ratings.",
  },
  mixed: {
    label: "part illustrative",
    color: "#e0b24a",
    hint: "Blends real ratings with illustrative (seeded) ones — read the spread with care.",
  },
  illustrative: {
    label: "illustrative",
    color: "#9a968e",
    hint: "No real rating covers this company yet; the figure is demo data.",
  },
};

// Single-character marks for dense table cells (see ScreenerTable.ProvMark).
export const PROVENANCE_MARK: Record<Provenance, string> = {
  real: "",
  mixed: "\u00b0",
  illustrative: "~",
};

// "MSCI and S&P real; Sustainalytics illustrative" — the sentence under a badge.
export const provenanceDetail = (
  contributing?: string[] | null,
  real?: string[] | null,
): string => {
  const LABEL: Record<string, string> = {
    msci: "MSCI", sp: "S&P", sustainalytics: "Sustainalytics", cdp: "CDP",
  };
  const used = contributing ?? [];
  if (!used.length) return "";
  const realSet = new Set(real ?? []);
  const isReal = used.filter((k) => realSet.has(k)).map((k) => LABEL[k] ?? k);
  const seeded = used.filter((k) => !realSet.has(k)).map((k) => LABEL[k] ?? k);
  const parts: string[] = [];
  if (isReal.length) parts.push(`${isReal.join(", ")} real`);
  if (seeded.length) parts.push(`${seeded.join(", ")} illustrative`);
  return parts.join(" · ");
};

export const signed = (v: number | null | undefined, dp = 1): string =>
  v === null || v === undefined ? "N.A." : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;

export const TOPIC_LABEL = (id: string): string =>
  id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
