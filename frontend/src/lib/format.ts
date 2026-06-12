export const clamp = (value: number, min = 0, max = 100) =>
  Math.min(max, Math.max(min, value));

export const round = (value: number, dp = 1) => {
  const factor = 10 ** dp;
  return Math.round(value * factor) / factor;
};

export const signed = (value: number, dp = 2) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(dp)}`;

export const percent = (value: number, dp = 2) => `${value.toFixed(dp)}%`;

export const signedPercent = (value: number, dp = 2) =>
  `${signed(value, dp)}%`;

export const usdBillions = (value: number) =>
  value >= 1000 ? `$${(value / 1000).toFixed(2)}T` : `$${value.toFixed(0)}B`;

export const compact = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
