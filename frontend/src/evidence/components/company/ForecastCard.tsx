import type { Forecast } from "../../types";
import { na } from "../../lib/ui";
import { HypothesisBadge } from "../common/badges";
import Why from "../common/Why";

// Ratings barely move, so the direction is the claim and the level is the detail — the
// card is ordered that way, and the reliability figure shown is the DIRECTIONAL one with
// the sample size it was measured on. When the fitted model failed to beat naive
// persistence the card says so instead of hiding it behind a number.
const DIRECTION_TONE: Record<string, string> = {
  "likely upgrade": "text-profit",
  "likely downgrade": "text-loss",
};

export default function ForecastCard({ forecast }: { forecast: Forecast }) {
  const fc = forecast;
  const maxAbs = Math.max(0.1, ...fc.feature_contributions.map((c) => Math.abs(c.contribution)));
  const tone = DIRECTION_TONE[fc.direction ?? ""] ?? "text-purpose";
  const reliability =
    fc.directional_accuracy != null
      ? `direction ${Math.round(fc.directional_accuracy * 100)}% of n=${fc.directional_n ?? "?"}`
      : "direction not yet measurable";

  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-txt">
            MSCI rating estimate{fc.target_year ? ` · ${fc.target_year}` : ""}
          </h3>
          <p className="text-[11px] text-faint">
            What the rater would likely say now, from news + evidence dated to the same period
          </p>
        </div>
        <HypothesisBadge note={`${fc.model_label ?? "model"} · ${reliability}`} />
      </div>

      {fc.predicted_score === null ? (
        <p className="mt-3 text-[12px] text-faint">
          No real MSCI rating disclosed for this company — no estimate (N.A.).
        </p>
      ) : (
        <>
          <div className="mt-3 flex items-end gap-3">
            <span className={`text-2xl font-semibold ${tone}`}>{fc.direction ?? "—"}</span>
            <span className="pb-1 font-mono text-[12px] text-muted">
              {fc.last_rating_label ?? "?"}
              {fc.last_rating_year ? ` (${fc.last_rating_year})` : ""} → {fc.predicted_label ?? na(fc.predicted_score)}
            </span>
            <span className="pb-1 ml-auto"><Why trace={fc.trace} title="Estimate drivers" /></span>
          </div>
          <p className="mt-1 font-mono text-[11px] text-faint">
            level {na(fc.predicted_score)} of 7 · CI {na(fc.ci_low)} – {na(fc.ci_high)} · {reliability}
          </p>

          {fc.baseline_only && (
            <p className="mt-2 rounded border border-hairline bg-base px-2 py-1.5 text-[11px] text-muted">
              This is the naive baseline, not a fitted model: {fc.model_label}.
            </p>
          )}

          {fc.feature_contributions.length > 0 && (
            <>
              <p className="mt-3 mb-1 text-[11px] font-medium text-faint">What's driving it</p>
              <div className="space-y-1">
                {fc.feature_contributions.slice(0, 6).map((c) => {
                  const pct = (Math.abs(c.contribution) / maxAbs) * 100;
                  const pos = c.contribution >= 0;
                  return (
                    <div key={c.feature} className="flex items-center gap-2 text-[11px]">
                      <span className="w-28 shrink-0 truncate text-muted">{c.feature}</span>
                      <div className="flex h-2 flex-1 items-center">
                        <div className="h-2 rounded" style={{
                          width: `${pct}%`,
                          backgroundColor: pos ? "#3ecf8e" : "#ef6f63",
                          opacity: 0.8,
                        }} />
                      </div>
                      <span className="w-10 text-right font-mono text-faint">
                        {c.contribution >= 0 ? "+" : ""}{c.contribution}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
