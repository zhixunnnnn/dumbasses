import type { QuadrantKey, RegQuality, VerifyState } from "../types";

export const QUADRANT: Record<
  QuadrantKey,
  { label: string; color: string; blurb: string; emoji: string }
> = {
  HIDDEN_WINNERS: {
    label: "Hidden Winners",
    color: "#3ecf8e",
    blurb: "Low score today, improving fast — the market hasn't priced it yet.",
    emoji: "🚀",
  },
  FUTURE_LEADERS: {
    label: "Future Leaders",
    color: "#4cc4d4",
    blurb: "High score and still improving — a compounding ESG moat.",
    emoji: "🌟",
  },
  VALUE_TRAPS: {
    label: "Value Traps",
    color: "#e0b24a",
    blurb: "Low score and declining — structural ESG risk.",
    emoji: "⚠️",
  },
  OVERRATED: {
    label: "Overrated Leaders",
    color: "#ec6a5e",
    blurb: "High score but deteriorating — the market still pays a premium.",
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

export const signed = (v: number | null | undefined, dp = 1): string =>
  v === null || v === undefined ? "N.A." : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;

export const TOPIC_LABEL = (id: string): string =>
  id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
