import type { Forecast } from "../../types";
import { na } from "../../lib/ui";
import { HypothesisBadge } from "../common/badges";
import Why from "../common/Why";

export default function ForecastCard({ forecast }: { forecast: Forecast }) {
  const fc = forecast;
  const maxAbs = Math.max(0.1, ...fc.feature_contributions.map((c) => Math.abs(c.contribution)));
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-txt">
            Live ESG estimate{fc.target_year ? ` · ${fc.target_year}` : ""}
          </h3>
          <p className="text-[11px] text-faint">Real-time, from current news + market signals</p>
        </div>
        <HypothesisBadge
          note={`Real-data Ridge model · LOO MAE ${na(fc.val_error)}${
            fc.directional_accuracy != null
              ? ` · ~${Math.round(fc.directional_accuracy * 100)}% hit-rate`
              : ""
          }`}
        />
      </div>

      {fc.predicted_score === null ? (
        <p className="mt-3 text-[12px] text-faint">Insufficient feature history — no forecast (N.A.).</p>
      ) : (
        <>
          <div className="mt-3 flex items-end gap-3">
            <span className="font-mono text-3xl font-semibold text-purpose">{na(fc.predicted_score)}</span>
            <span className="pb-1 font-mono text-[11px] text-faint">
              CI {na(fc.ci_low)} – {na(fc.ci_high)}
              {fc.directional_accuracy != null && (
                <> · <span className="text-muted">~{Math.round(fc.directional_accuracy * 100)}% hit-rate (LOO, n=10)</span></>
              )}
            </span>
            <span className="pb-1 ml-auto"><Why trace={fc.trace} title="Estimate drivers" /></span>
          </div>

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
    </div>
  );
}
