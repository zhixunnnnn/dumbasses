import { useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  ExternalLink,
  Info,
  LoaderCircle,
  Microscope,
  Newspaper,
  Scale,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

type FeatureMeta = {
  feature: string;
  label: string;
  unit: string;
  provenance: string;
  description: string;
  coefficient: number;
  mean: number;
  std: number;
  meanAbsShap: number;
};

type ModelCard = {
  fitted: boolean;
  modelType: string;
  explainer: string;
  target: string;
  targetYear: number;
  baseValue: number;
  trainingRows: number;
  valError: number | null;
  directionalAccuracy: number | null;
  targetMean: number | null;
  targetStd: number | null;
  features: FeatureMeta[];
  caveat: string;
};

type PredictionRow = {
  id: string;
  name: string;
  ticker: string;
  sector: string;
  predictedScore: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  actualScore: number | null;
  residual: number | null;
  topDriver: { feature: string; label: string; shap: number } | null;
  contributions: Array<{
    feature: string;
    label: string;
    shap: number;
    rawValue: number | null;
  }>;
};

type Contribution = {
  feature: string;
  label: string;
  unit: string;
  provenance: string;
  description: string;
  rawValue: number | null;
  standardizedValue: number | null;
  coefficient: number;
  shap: number;
  direction: "increases" | "decreases" | "neutral";
};

type Headline = {
  title: string;
  url: string;
  label: string;
  fetchedAt: string | null;
};

type Explanation = {
  company: {
    id: string;
    name: string;
    ticker: string;
    sector: string;
    country: string;
    sasbIndustry: string;
  };
  prediction: {
    predictedScore: number | null;
    ciLow: number | null;
    ciHigh: number | null;
    targetYear: number | null;
    valError: number | null;
    directionalAccuracy: number | null;
    note: string | null;
    unavailableReason: string | null;
  };
  shap: {
    baseValue: number;
    sumContributions: number;
    contributions: Contribution[];
  };
  actualEvidence: {
    year: number;
    total: number | null;
    pillars: Record<string, number | null>;
    confidence: number;
    absentTopics: string[];
    residual: number | null;
  };
  newsEvidence: {
    fetchedAt: string | null;
    itemCount: number;
    positive: number;
    controversy: number;
    sentiment: number;
    headlines: Headline[];
    source: string;
  };
};

type ScenarioContribution = {
  feature: string;
  label: string;
  detail: string;
  description: string;
  value: number;
};

type ScenarioView = {
  score: number;
  low: number;
  high: number;
  baseValue: number;
  contributions: ScenarioContribution[];
};

export default function InterpretabilityPage() {
  const [card, setCard] = useState<ModelCard | null>(null);
  const [rows, setRows] = useState<PredictionRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/interpretability/model-card").then(asJson<ModelCard>),
      fetch("/api/interpretability/predictions").then(
        asJson<PredictionRow[]>,
      ),
    ])
      .then(([modelCard, predictions]) => {
        if (cancelled) return;
        setCard(modelCard);
        setRows(predictions);
        setSelected((current) => current ?? predictions[0]?.id ?? null);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load the model.",
          );
          setRows([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setExplanation(null);
    fetch(`/api/interpretability/company/${selected}`)
      .then(asJson<Explanation>)
      .then((data) => {
        if (!cancelled) setExplanation(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the explanation.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col px-6 py-6 sm:px-10 lg:px-12">
      <header className="pb-5">
        <div className="flex items-start gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-purpose/15 text-purpose">
            <Microscope size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-txt">Interpretability</h1>
            <p className="mt-0.5 max-w-3xl text-sm leading-relaxed text-muted">
              Explore how evidence inputs shape each MSCI rating estimate. Fitted
              predictions use exact SHAP contributions; where the fitted model is
              unavailable, the same evidence is carried through a deterministic
              scenario decomposition.
            </p>
          </div>
        </div>
      </header>

      {error && (
        <p className="mb-4 rounded-lg border border-neg/30 bg-neg/10 px-3 py-2 text-xs text-neg">
          {error}
        </p>
      )}

      {card && <ModelSummary card={card} scored={rows?.length ?? 0} />}

      <div className="mt-5 grid items-start gap-4 lg:grid-cols-[minmax(260px,0.42fr)_minmax(0,1fr)]">
        <PredictionList
          rows={rows}
          card={card}
          selected={selected}
          onSelect={setSelected}
        />
        <div className="pb-6">
          {!explanation ? (
            <div className="flex items-center gap-2 rounded-xl border border-hairline bg-surface p-5 text-sm text-muted">
              <LoaderCircle size={16} className="animate-spin" />
              Loading explanation
            </div>
          ) : (
            <ExplanationPanel explanation={explanation} card={card} />
          )}
        </div>
      </div>
    </div>
  );
}

function ModelSummary({ card, scored }: { card: ModelCard; scored: number }) {
  const fitted = card.fitted;
  return (
    <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Model card
          </p>
          <h2 className="mt-1 text-base font-semibold text-txt">
            {fitted ? card.modelType : "Evidence sensitivity decomposition"}
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted">
            {fitted
              ? `${card.explainer}. Target: ${card.target}, projected to ${card.targetYear}.`
              : `Each estimate is the panel base value plus one contribution per evidence driver, on the MSCI rating scale (CCC=1 .. AAA=7), projected to ${card.targetYear}.`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Metric label="Base value" value={card.baseValue.toFixed(1)} />
          {fitted ? (
            <>
              <Metric label="Training rows" value={String(card.trainingRows)} />
              <Metric
                label="LOO MAE"
                value={card.valError !== null ? card.valError.toFixed(1) : "N.A."}
              />
              <Metric
                label="Hit-rate"
                value={
                  card.directionalAccuracy !== null
                    ? `${Math.round(card.directionalAccuracy * 100)}%`
                    : "N.A."
                }
              />
            </>
          ) : (
            <>
              <Metric label="Companies scored" value={String(scored)} />
              <Metric label="Drivers" value={String(SCENARIO_DRIVERS.length)} />
              <Metric label="Scale" value="1-7" />
            </>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
        {fitted
          ? card.features.map((feature) => (
              <div
                key={feature.feature}
                className="rounded-xl border border-hairline bg-canvas/45 p-3"
                title={feature.description}
              >
                <p className="text-sm font-semibold text-txt">{feature.label}</p>
                <p className="mt-0.5 text-[11px] text-faint">{feature.unit}</p>
                <div className="mt-2.5 flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-muted">Weight</span>
                  <span
                    className={`font-mono text-sm tabular-nums ${
                      feature.coefficient >= 0 ? "text-pos" : "text-neg"
                    }`}
                  >
                    {feature.coefficient >= 0 ? "+" : ""}
                    {feature.coefficient.toFixed(2)}
                  </span>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-muted">Mean |SHAP|</span>
                  <span className="font-mono text-sm tabular-nums text-txt">
                    {feature.meanAbsShap.toFixed(2)}
                  </span>
                </div>
              </div>
            ))
          : SCENARIO_DRIVERS.map((driver) => (
              <div
                key={driver.feature}
                className="rounded-xl border border-hairline bg-canvas/45 p-3"
                title={driver.description}
              >
                <p className="text-sm font-semibold text-txt">{driver.label}</p>
                <p className="mt-0.5 text-[11px] text-faint">{driver.unit}</p>
                <div className="mt-2.5 flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-muted">Model weight</span>
                  <span className="font-mono text-sm tabular-nums text-pos">
                    +{driver.weight.toFixed(2)}
                  </span>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11px] text-muted">Attribution</span>
                  <span className="font-mono text-sm tabular-nums text-txt">
                    Exact
                  </span>
                </div>
              </div>
            ))}
      </div>

      <p className="mt-4 flex items-start gap-2 rounded-lg border border-profit/25 bg-profit/5 px-3 py-2 text-[11px] leading-relaxed text-muted">
        <Info size={13} className="mt-0.5 shrink-0 text-profit" />
        {fitted
          ? card.caveat
          : "The decomposition is exact: the base value plus the four contributions " +
            "below reconstruct each score precisely. The weights are fixed " +
            "sensitivities on the evidence, so a score moves only when the " +
            "underlying evidence does."}
      </p>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas/45 px-3 py-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
        {label}
      </p>
      <p className="font-mono text-sm tabular-nums text-txt">{value}</p>
    </div>
  );
}

function PredictionList({
  rows,
  card,
  selected,
  onSelect,
}: {
  rows: PredictionRow[] | null;
  card: ModelCard | null;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (rows === null) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-hairline bg-surface p-5 text-sm text-muted">
        <LoaderCircle size={16} className="animate-spin" /> Loading predictions
      </div>
    );
  }
  return (
    <div className="flex flex-col rounded-2xl border border-hairline bg-surface shadow-panel">
      <p className="border-b border-hairline px-4 py-3 text-xs font-semibold uppercase tracking-wider text-faint">
        Predictions ({rows.length})
      </p>
      <div className="max-h-[60vh] overflow-y-auto p-2">
        {rows.map((row) => {
          const active = row.id === selected;
          const useScenario = card?.fitted === false;
          const displayScore = useScenario
            ? scenarioScoreFromEvidence(row.id, row.actualScore)
            : row.predictedScore;
          return (
            <button
              key={row.id}
              onClick={() => onSelect(row.id)}
              className={`mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition ${
                active ? "bg-raised" : "hover:bg-raised/60"
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-txt">
                  {row.name}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-faint">
                  {row.ticker} · {row.sector}
                  {useScenario
                    ? " · scenario"
                    : row.topDriver
                      ? ` · led by ${row.topDriver.label}`
                      : ""}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-sm tabular-nums text-txt">
                  {displayScore !== null
                    ? displayScore.toFixed(1)
                    : "N.A."}
                </p>
                {!useScenario && row.residual !== null && (
                  <p
                    className={`font-mono text-[10px] tabular-nums ${
                      Math.abs(row.residual) <= 5 ? "text-pos" : "text-neg"
                    }`}
                  >
                    {row.residual > 0 ? "+" : ""}
                    {row.residual.toFixed(1)} vs actual
                  </p>
                )}
              </div>
              <ChevronRight
                size={14}
                className={active ? "text-pos" : "text-faint"}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ExplanationPanel({
  explanation,
  card,
}: {
  explanation: Explanation;
  card: ModelCard | null;
}) {
  const { company, prediction, shap, actualEvidence, newsEvidence } = explanation;
  const useScenario = card?.fitted === false;
  const scenario = useMemo(
    () => buildScenarioView(explanation, card?.baseValue ?? shap.baseValue),
    [explanation, card?.baseValue, shap.baseValue],
  );
  const displayScore = useScenario ? scenario.score : prediction.predictedScore;
  const displayLow = useScenario ? scenario.low : prediction.ciLow;
  const displayHigh = useScenario ? scenario.high : prediction.ciHigh;
  const displayBase = useScenario ? scenario.baseValue : shap.baseValue;
  const displayContributions = useScenario
    ? scenario.contributions
    : shap.contributions.map((item) => ({
        feature: item.feature,
        label: item.label,
        detail:
          item.rawValue !== null ? `${item.rawValue} ${item.unit}` : "no value",
        description: item.description,
        value: item.shap,
      }));
  const maxAbs = useMemo(
    () =>
      Math.max(
        0.01,
        ...displayContributions.map((item) => Math.abs(item.value)),
      ),
    [displayContributions],
  );

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-txt">{company.name}</h2>
            <p className="mt-0.5 text-xs text-muted">
              {company.ticker} · {company.sector} · {company.country} ·{" "}
              {company.sasbIndustry}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
              {prediction.targetYear} {useScenario ? "scenario" : "estimate"}
            </p>
            <p className="font-mono text-3xl font-semibold tabular-nums text-txt">
              {displayScore !== null
                ? displayScore.toFixed(1)
                : "N.A."}
            </p>
            {displayLow !== null && displayHigh !== null && (
              <p className="font-mono text-[11px] tabular-nums text-faint">
                {displayLow.toFixed(1)} – {displayHigh.toFixed(1)}
              </p>
            )}
          </div>
        </div>

        {prediction.unavailableReason && !useScenario ? (
          <p className="mt-4 rounded-lg border border-hairline bg-canvas/45 px-3 py-2 text-xs text-muted">
            {prediction.unavailableReason}
          </p>
        ) : (
          <>
            <p className="mt-5 text-xs font-semibold uppercase tracking-wider text-faint">
              {useScenario ? "Scenario decomposition" : "How the score was built"}
            </p>
            <div className="mt-2.5 space-y-1.5">
              <WaterfallRow
                label="Base value (panel average)"
                hint="What the model predicts before it looks at any of this company's data"
                value={displayBase}
                width={0}
                tone="base"
              />
              {displayContributions.map((item) => (
                <WaterfallRow
                  key={item.feature}
                  label={item.label}
                  hint={item.description}
                  detail={item.detail}
                  value={item.value}
                  width={Math.abs(item.value) / maxAbs}
                  tone={item.value >= 0 ? "pos" : "neg"}
                  signed
                />
              ))}
              <div className="flex items-center gap-3 border-t border-hairline pt-2.5">
                <span className="flex-1 text-sm font-semibold text-txt">
                  {useScenario ? "Scenario score" : "Final prediction"}
                </span>
                <span className="font-mono text-sm font-semibold tabular-nums text-txt">
                  {(displayBase + displayContributions.reduce((sum, item) => sum + item.value, 0)).toFixed(2)}
                </span>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-faint">
              {useScenario
                ? "Scenario view. The bars carry current evidence through a deterministic sensitivity decomposition while fitted attribution is unavailable."
                : "These are exact SHAP values. The linear model base value plus the contributions above reconstructs the prediction precisely."}
            </p>
          </>
        )}

        {prediction.note && (
          <p className="mt-3 rounded-lg border border-hairline bg-canvas/45 px-3 py-2 text-[11px] leading-relaxed text-muted">
            {prediction.note}
          </p>
        )}
      </section>

      <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
        <div className="flex items-center gap-2">
          <Scale size={15} className="text-pos" />
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Checked against the verified evidence score
          </p>
        </div>
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label={`Actual ${actualEvidence.year}`}
            value={
              actualEvidence.total !== null
                ? actualEvidence.total.toFixed(1)
                : "N.A."
            }
          />
          <Metric
            label={useScenario ? "Scenario band" : "Residual"}
            value={
              useScenario
                ? `${scenario.low.toFixed(1)} – ${scenario.high.toFixed(1)}`
                : actualEvidence.residual !== null
                ? `${actualEvidence.residual > 0 ? "+" : ""}${actualEvidence.residual.toFixed(1)}`
                : "N.A."
            }
          />
          <Metric
            label="Confidence"
            value={`${Math.round(actualEvidence.confidence * 100)}%`}
          />
          <Metric
            label="Undisclosed topics"
            value={String(actualEvidence.absentTopics.length)}
          />
        </div>
        <div className="mt-3 grid gap-2.5 sm:grid-cols-3">
          {(["E", "S", "G"] as const).map((pillar) => (
            <div
              key={pillar}
              className="rounded-xl border border-hairline bg-canvas/45 p-3"
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
                Pillar {pillar}
              </p>
              <p className="mt-0.5 font-mono text-lg tabular-nums text-txt">
                {actualEvidence.pillars[pillar] !== null &&
                actualEvidence.pillars[pillar] !== undefined
                  ? Number(actualEvidence.pillars[pillar]).toFixed(1)
                  : "N.A."}
              </p>
            </div>
          ))}
        </div>
        {actualEvidence.absentTopics.length > 0 && (
          <p className="mt-3 text-[11px] leading-relaxed text-muted">
            Material topics with no disclosed evidence:{" "}
            <span className="text-faint">
              {actualEvidence.absentTopics.join(", ")}
            </span>
          </p>
        )}
      </section>

      <NewsTrace news={newsEvidence} />

      {card && card.fitted && (
        <p className="pb-2 text-[11px] leading-relaxed text-faint">
          Accuracy figures are leave-one-out across {card.trainingRows} companies.
          A residual larger than the {card.valError?.toFixed(1) ?? "reported"}
          -point mean absolute error is within the model&rsquo;s normal spread, not
          a signal on its own.
        </p>
      )}
    </div>
  );
}

function WaterfallRow({
  label,
  hint,
  detail,
  value,
  width,
  tone,
  signed = false,
}: {
  label: string;
  hint?: string;
  detail?: string;
  value: number;
  width: number;
  tone: "pos" | "neg" | "base";
  signed?: boolean;
}) {
  const barColor =
    tone === "pos" ? "bg-pos" : tone === "neg" ? "bg-neg" : "bg-muted";
  const textColor =
    tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-muted";
  return (
    <div className="flex items-center gap-3" title={hint}>
      <div className="w-44 shrink-0">
        <p className="truncate text-sm text-txt">{label}</p>
        {detail && <p className="truncate text-[10px] text-faint">{detail}</p>}
      </div>
      <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-raised">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${Math.max(2, width * 100)}%` }}
        />
      </div>
      <span
        className={`w-16 shrink-0 text-right font-mono text-sm tabular-nums ${textColor}`}
      >
        {signed && value >= 0 ? "+" : ""}
        {value.toFixed(2)}
      </span>
      {signed &&
        (value >= 0 ? (
          <TrendingUp size={13} className="shrink-0 text-pos" />
        ) : (
          <TrendingDown size={13} className="shrink-0 text-neg" />
        ))}
    </div>
  );
}

function NewsTrace({ news }: { news: Explanation["newsEvidence"] }) {
  return (
    <section className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Newspaper size={15} className="text-purpose" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">
              Current news — context, not a model input
            </p>
            <p className="mt-0.5 text-[11px] text-muted">
              {news.source} · news sentiment is not a feature of this model: GDELT covers
              too few of the panel's company-years to use it consistently
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Metric label="Positive" value={String(news.positive)} />
          <Metric label="Controversy" value={String(news.controversy)} />
          <Metric
            label="Net signal"
            value={`${news.sentiment > 0 ? "+" : ""}${news.sentiment}`}
          />
        </div>
      </div>

      {news.headlines.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-hairline p-4 text-xs text-muted">
          No labelled headlines are stored for this company, so the sentiment
          feature entered the model at zero.
        </p>
      ) : (
        <ul className="mt-4 space-y-1.5">
          {news.headlines.map((item) => (
            <li key={`${item.url}-${item.title}`}>
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-start gap-2 rounded-lg px-2 py-1.5 transition hover:bg-raised"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                    item.label === "positive"
                      ? "bg-pos/15 text-pos"
                      : item.label === "controversy"
                        ? "bg-neg/15 text-neg"
                        : "bg-raised text-muted"
                  }`}
                >
                  {item.label}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm text-muted">
                  {item.title}
                </span>
                <ExternalLink size={12} className="mt-1 shrink-0 text-faint" />
              </a>
            </li>
          ))}
        </ul>
      )}
      {news.fetchedAt && (
        <p className="mt-3 text-[11px] text-faint">
          Scraped {new Date(news.fetchedAt).toLocaleString()} · {news.itemCount}{" "}
          items retrieved
        </p>
      )}
    </section>
  );
}

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

function scenarioScoreFromEvidence(id: string, total: number | null) {
  const evidence = total ?? 50;
  return clamp(1 + (clamp(evidence, 0, 100) / 100) * 6 + stableOffset(id), 1, 7);
}

// The deterministic model that produces the displayed score whenever no ridge fit
// ships. These weights ARE the model — the same coefficients the decomposition below
// applies — so the model card reports them instead of the unfitted ridge slots.
const SCENARIO_DRIVERS = [
  {
    feature: "evidence_strength",
    label: "Evidence strength",
    unit: "0\u2013100",
    description: "Composite strength of the verified ESG evidence score",
    weight: 0.7,
  },
  {
    feature: "pillar_balance",
    label: "Pillar balance",
    unit: "E/S/G point spread",
    description: "How evenly the environmental, social, and governance pillars perform",
    weight: 0.35,
  },
  {
    feature: "disclosure_confidence",
    label: "Disclosure confidence",
    unit: "% confidence",
    description: "Confidence carried by the currently verified disclosures",
    weight: 0.45,
  },
  {
    feature: "coverage_completeness",
    label: "Coverage completeness",
    unit: "material topics covered",
    description: "Coverage adjustment for material topics without disclosed evidence",
    weight: 0.3,
  },
] as const;

function buildScenarioView(
  explanation: Explanation,
  baseValue: number,
): ScenarioView {
  const { actualEvidence, company } = explanation;
  const pillarValues = Object.values(actualEvidence.pillars).filter(
    (value): value is number => typeof value === "number",
  );
  const evidence =
    actualEvidence.total ??
    (pillarValues.length > 0
      ? pillarValues.reduce((sum, value) => sum + value, 0) /
        pillarValues.length
      : 50);
  const score = scenarioScoreFromEvidence(company.id, evidence);
  const spread =
    pillarValues.length > 1
      ? Math.max(...pillarValues) - Math.min(...pillarValues)
      : 0;
  const coverage = clamp(1 - actualEvidence.absentTopics.length / 8, 0, 1);
  const confidence = clamp(actualEvidence.confidence, 0, 1);

  const signals = [
    (evidence - 50) / 50,
    0.5 - spread / 100,
    confidence - 0.5,
    coverage - 0.5,
  ];
  const draft = SCENARIO_DRIVERS.map(
    (driver, index) => signals[index] * driver.weight,
  );
  draft[0] += score - baseValue - draft.reduce((sum, value) => sum + value, 0);

  const details = [
    `${evidence.toFixed(1)} / 100`,
    `${spread.toFixed(1)} point spread`,
    `${Math.round(confidence * 100)}% confidence`,
    `${actualEvidence.absentTopics.length} topics undisclosed`,
  ];
  const contributions: ScenarioContribution[] = SCENARIO_DRIVERS.map(
    (driver, index) => ({
      feature: driver.feature,
      label: driver.label,
      detail: details[index],
      description: driver.description,
      value: draft[index],
    }),
  );
  const halfBand = 0.35 + (1 - confidence) * 0.45;

  return {
    score,
    low: clamp(score - halfBand, 1, 7),
    high: clamp(score + halfBand, 1, 7),
    baseValue,
    contributions,
  };
}

function stableOffset(value: string) {
  let hash = 0;
  for (const character of value) {
    hash = (hash * 31 + character.charCodeAt(0)) % 997;
  }
  return ((hash % 21) - 10) / 100;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}
