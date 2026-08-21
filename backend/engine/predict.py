"""predict — estimate the RATER's ESG rating (MSCI level) from real, dated signals.

Two models over the same panel, both built only from data that existed at the row's own
time. Nothing here is seeded, imputed or carried forward.

  NOWCAST (primary)   features of year t  ->  the REAL MSCI rating of year t.
                      Applied to the current year it answers "what would MSCI say about
                      this company today", ahead of the rater's own publication lag.

  LEADING (secondary) features of year t  ->  the REAL MSCI rating of year t+1, with the
                      rating at t as a feature. This is the one that tests whether news
                      and evidence LEAD a rating change.

Every feature is contemporaneous with its row's year:
    news_sentiment   GDELT DOC 2.0 headlines PUBLISHED in year t, labelled by the repo's
                     own classifier (backend/data/gdeltnews.py). The 2026 news snapshot in
                     the database is not back-filled into 2021 rows — and by the same rule
                     the current-year row is fetched from GDELT for the current year, so
                     train and inference build the feature identically.
    evidence_total   the evidence score for year t, from THAT year's own report.
    price_return     trailing 1-year return of the weekly close series, clipped at t.
    volatility       annualised weekly-return volatility, clipped at t.

The target is the MSCI letter the company disclosed in its own report, mapped through
config.MSCI_LETTER_TO_NUM (CCC=1 .. AAA=7). A rating percentile would need
config.MIN_PEERS_FOR_SECTOR_RANK companies rated in the same year, which this panel only
reaches in one year, so the raw level is the honest target.

POOLED-TARGET ATTEMPT (2026-08, negative — do not redo without new data). The MSCI-only
nowcast panel has n=4 and zero target variance, so the other disclosed channels were pooled:
one row per (company, year, rater) over msci / sustainalytics / sp / cdp, each oriented so
higher = better and then z-scored WITHIN its channel, which makes an MSCI AAA and an S&P 58
comparable and — by construction — absorbs the per-rater intercept, so no rater dummies are
needed (adding them was tried and was strictly worse, MAE 0.99-1.18 vs 0.92-0.98).
Index memberships (DJSI, FTSE4Good) stayed out; they are not ratings.
That panel reaches 20 rows with real target and real features, and the target does have
genuine variance (MSCI A/AA/AAA, S&P 52-58, Sustainalytics 19.1-19.8, CDP C/B-/B/A).
news_sentiment had to be dropped from the whole panel: GDELT is currently returning
"API unavailable" for every year of the companies the pooled rows need, and keeping the
feature would have cut the panel back to the same 4 MSCI rows. Consistency beat the feature.
Because the four rater rows of one company-year share an identical feature vector, the
evaluation used GROUP leave-one-out (a whole company-year held out at once); plain LOO here
leaks a row's twin into its own training set.
RESULT: directional accuracy on the n=8 rows with a prior same-channel rating was 62.5%,
exactly equal to the naive "hold" baseline of 62.5% (p=0.65), at every ridge alpha and every
move threshold tried. Level MAE 0.92-0.99 z, worse than persistence (0.62) and worse than the
panel mean (0.89). It did not BEAT persistence, so it did not ship. The pooled LEADING panel
(same channel at t and t+1) has only 3 rows and is not evaluable at all.
The code below is therefore unchanged: the labelled persistence baseline still serves.

ACCEPTANCE: ratings are sticky, so the bar is DIRECTION, not precision — the fitted model
ships only if its leave-one-out directional accuracy beats the naive baselines (persistence
and panel mean). Otherwise `forecast()` returns the naive prediction, labelled as such.
Run `python -m backend.engine.predict` for the full evaluation report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb
from typing import Optional

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import config
from .ingest import Dataset
from .llm import LLMClient, MockLLMClient
from .models import FeatureContribution, Forecast, TraceNode
from .score import evidence_score

FEATURES = ["news_sentiment", "evidence_total", "price_return", "volatility"]
LEADING_FEATURES = FEATURES + ["rating_level"]
RIDGE_ALPHAS = (0.3, 1.0, 3.0, 10.0, 30.0)     # tuned on the LOO fit, reported as such
RIDGE_ALPHA = 3.0                              # fallback when there is nothing to tune on
MIN_EVALUABLE_ROWS = 4                         # below this a leave-one-out fit is meaningless
NUM_TO_MSCI = {v: k for k, v in config.MSCI_LETTER_TO_NUM.items()}


# --------------------------------------------------------------------------- #
# real inputs
# --------------------------------------------------------------------------- #
def real_ratings() -> dict[str, dict[int, int]]:
    """{cid: {year: msci_level}} — REAL disclosed MSCI letters only, mapped to 1..7."""
    from backend.data.realratings import scored_by_year

    out: dict[str, dict[int, int]] = {}
    for cid, years in scored_by_year().items():
        for year, raters in years.items():
            row = raters.get("msci")
            level = config.MSCI_LETTER_TO_NUM.get(str(row["value_raw"]).upper()) if row else None
            if level is not None:
                out.setdefault(cid, {})[year] = level
    return out


def _real_evidence_year(cid: str, year: int) -> bool:
    """True only when that year's OWN report was extracted — a seeded document year is
    not a real feature and must not enter the panel."""
    try:
        from backend.data.realclaims import cached_claims_for

        return cached_claims_for(cid, year=year) is not None
    except Exception:
        return False


def _price_features(ds: Dataset, cid: str, year: int) -> Optional[tuple[float, float]]:
    """Trailing 1-year return and annualised volatility, using only closes on or before
    the last day of `year` — no post-target price ever reaches a feature."""
    closes = [c.close for c in ds.prices.get(cid, [])
              if c.close and c.week_date <= f"{year}-12-31"]
    if len(closes) < 12:
        return None
    window = closes[-52:]
    ret = (window[-1] / window[0] - 1.0) * 100.0
    vol = float(np.std(np.diff(np.log(window))) * np.sqrt(52) * 100.0)
    return ret, vol


def _features_at(ds: Dataset, cid: str, year: int, client: LLMClient) -> Optional[list[float]]:
    """The four contemporaneous features for one company-year, or None if any is missing.
    Missing is missing: no zero-fill, no nearest-year substitute."""
    from backend.data import gdeltnews

    news = gdeltnews.sentiment_at(cid, year)
    prices = _price_features(ds, cid, year)
    if news is None or prices is None or not _real_evidence_year(cid, year):
        return None
    evidence = evidence_score(ds, cid, year, client).total
    if evidence is None:
        return None
    return [float(news), float(evidence), float(prices[0]), float(prices[1])]


# --------------------------------------------------------------------------- #
# panels
# --------------------------------------------------------------------------- #
@dataclass
class Panel:
    X: np.ndarray
    y: np.ndarray
    keys: list[tuple[str, int]]           # (company_id, feature year)
    prev: list[Optional[int]]             # last rating known BEFORE the target year
    features: list[str]

    def __len__(self) -> int:
        return len(self.y)


def _panel_rows(ds: Dataset, client: LLMClient, horizon: int) -> Panel:
    """horizon=0 -> nowcast (target year == feature year); horizon=1 -> leading.

    A row exists only where the target is a REAL extracted rating AND every feature at the
    feature year is real. The leading panel additionally carries the rating at t.
    """
    ratings = real_ratings()
    features = FEATURES if horizon == 0 else LEADING_FEATURES
    X, y, keys, prev = [], [], [], []
    for cid, by_year in sorted(ratings.items()):
        for target_year, level in sorted(by_year.items()):
            feature_year = target_year - horizon
            row = _features_at(ds, cid, feature_year, client)
            if row is None:
                continue
            if horizon:
                at_t = by_year.get(feature_year)
                if at_t is None:
                    continue
                row = row + [float(at_t)]
            earlier = [yr for yr in by_year if yr < target_year]
            X.append(row)
            y.append(float(level))
            keys.append((cid, feature_year))
            prev.append(by_year[max(earlier)] if earlier else None)
    return Panel(np.array(X, float).reshape(len(y), len(features)),
                 np.array(y, float), keys, prev, features)


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #
@dataclass
class Evaluation:
    n: int = 0
    mae: Optional[float] = None
    baseline_mae_persistence: Optional[float] = None
    persistence_n: int = 0                    # rows that HAVE a prior rating to persist
    mae_on_persistence_rows: Optional[float] = None   # the model, on those same rows
    baseline_mae_mean: Optional[float] = None
    side_acc: Optional[float] = None          # above/below the panel median
    side_n: int = 0
    side_baseline: Optional[float] = None
    move_acc: Optional[float] = None          # up/hold/down vs the last known rating
    move_n: int = 0
    move_baseline: Optional[float] = None     # the naive "hold" call
    p_value: Optional[float] = None           # binomial: could the edge be luck?
    alpha: float = RIDGE_ALPHA
    preds: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _binomial_tail(correct: int, n: int, p0: float) -> Optional[float]:
    """P(at least `correct` right | baseline rate p0). With ten rows almost nothing is
    significant, and this number is what says so out loud."""
    if n <= 0:
        return None
    p0 = min(max(p0, 1e-6), 1 - 1e-6)
    return float(sum(comb(n, k) * p0 ** k * (1 - p0) ** (n - k) for k in range(correct, n + 1)))


def _loo_predictions(panel: Panel, alpha: float) -> np.ndarray:
    """Leave-one-out: every prediction comes from a fit that never saw its own row."""
    preds = np.zeros(len(panel))
    idx = np.arange(len(panel))
    for i in idx:
        mask = idx != i
        scaler = StandardScaler().fit(panel.X[mask])
        model = Ridge(alpha=alpha).fit(scaler.transform(panel.X[mask]), panel.y[mask])
        preds[i] = model.predict(scaler.transform(panel.X[i:i + 1]))[0]
    return preds


def _move(delta: float, eps: float = config.RATING_MOVE_EPS) -> int:
    return 0 if abs(delta) < eps else (1 if delta > 0 else -1)


def evaluate(panel: Panel) -> Evaluation:
    """Honest leave-one-out evaluation, headlined by DIRECTION.

    Two directional questions are asked, because a sticky target makes level accuracy
    almost meaningless on its own:
      * side  — is the rating above or below the panel median (the nowcast's question)?
      * move  — up, down or unchanged against the company's last known rating (the
                question a rating desk actually cares about); the naive baseline calls
                "hold" every time and is hard to beat.
    """
    ev = Evaluation(n=len(panel))
    if len(panel) < MIN_EVALUABLE_ROWS:
        ev.notes.append(f"{len(panel)} real rows — too few even to cross-validate")
        return ev
    if len(panel) < config.MIN_FORECAST_ROWS:
        # still measured, and still reported: the numbers below are what the data can
        # say, they just do not clear the bar for shipping a fit.
        ev.notes.append(f"{len(panel)} real rows — below the {config.MIN_FORECAST_ROWS}-row "
                        "floor for shipping a fitted model")

    best = min(RIDGE_ALPHAS,
               key=lambda a: float(np.mean(np.abs(_loo_predictions(panel, a) - panel.y))))
    ev.alpha = best
    preds = _loo_predictions(panel, best)
    ev.preds = [float(p) for p in preds]
    ev.mae = float(np.mean(np.abs(preds - panel.y)))
    ev.notes.append(f"alpha={best} chosen on the LOO error itself — mildly optimistic")

    # baseline 1: the company's own last known rating; baseline 2: the panel mean
    # persistence only exists where a prior rating does, so the model is scored on the
    # SAME rows — otherwise the two MAEs are not comparable
    subset = [i for i, p in enumerate(panel.prev) if p is not None]
    ev.persistence_n = len(subset)
    if subset:
        ev.baseline_mae_persistence = float(np.mean([abs(panel.prev[i] - panel.y[i]) for i in subset]))
        ev.mae_on_persistence_rows = float(np.mean([abs(preds[i] - panel.y[i]) for i in subset]))
    ev.baseline_mae_mean = float(np.mean(np.abs(panel.y - np.mean(panel.y))))

    median = float(np.median(panel.y))
    side_hits = (preds > median) == (panel.y > median)
    ev.side_n = len(panel)
    ev.side_acc = float(np.mean(side_hits))
    # the baseline that guesses the more common side every time
    share = float(np.mean(panel.y > median))
    ev.side_baseline = max(share, 1.0 - share)

    moves = [(i, p) for i, p in enumerate(panel.prev) if p is not None]
    if moves:
        truth = [_move(panel.y[i] - p) for i, p in moves]
        called = [_move(preds[i] - p) for i, p in moves]
        ev.move_n = len(moves)
        ev.move_acc = float(np.mean([a == b for a, b in zip(truth, called)]))
        ev.move_baseline = float(np.mean([t == 0 for t in truth]))   # always "hold"
        ev.p_value = _binomial_tail(int(round(ev.move_acc * ev.move_n)), ev.move_n,
                                    ev.move_baseline)
    else:
        ev.p_value = _binomial_tail(int(round((ev.side_acc or 0) * ev.side_n)), ev.side_n,
                                    ev.side_baseline or 0.5)
    return ev


def beats_baseline(ev: Evaluation) -> bool:
    """Ship the fitted model only if it is directionally better than doing nothing."""
    if ev.n < config.MIN_FORECAST_ROWS or ev.side_acc is None:
        return False
    if ev.move_acc is not None and ev.move_baseline is not None:
        return ev.move_acc > ev.move_baseline
    return ev.side_acc > (ev.side_baseline or 0.5)


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
@dataclass
class _Model:
    ridge: Optional[Ridge]
    scaler: Optional[StandardScaler]
    val_error: Optional[float]
    directional_accuracy: Optional[float]     # the DIRECTIONAL figure, not a level hit-rate
    directional_n: int
    means: np.ndarray
    stds: np.ndarray
    fitted: bool                              # False -> forecast() serves the baseline
    rows: int
    evaluation: Evaluation
    leading: Evaluation
    ratings: dict[str, dict[int, int]]
    stamp: dict                               # END_YEAR + data fingerprint (staleness guard)


def data_fingerprint() -> dict:
    """What the model was trained on. Stamped into the joblib so a moved window or a
    re-extraction cannot silently keep serving yesterday's fit."""
    import hashlib

    ratings = real_ratings()
    blob = repr(sorted((cid, tuple(sorted(years.items()))) for cid, years in ratings.items()))
    return {"end_year": config.END_YEAR, "current_year": config.CURRENT_YEAR,
            "features": FEATURES,
            "ratings_sha1": hashlib.sha1(blob.encode()).hexdigest()[:12],
            "rating_rows": sum(len(y) for y in ratings.values())}


def train(ds: Dataset, client: Optional[LLMClient] = None) -> _Model:
    client = client or MockLLMClient()
    panel = _panel_rows(ds, client, horizon=0)
    leading = evaluate(_panel_rows(ds, client, horizon=1))
    ev = evaluate(panel)
    ratings = real_ratings()
    accuracy = ev.move_acc if ev.move_acc is not None else ev.side_acc
    accuracy_n = ev.move_n if ev.move_acc is not None else ev.side_n

    if not len(panel):
        empty = np.zeros(len(FEATURES))
        return _Model(None, None, None, None, 0, empty, np.ones(len(FEATURES)),
                      False, 0, ev, leading, ratings, data_fingerprint())

    scaler = StandardScaler().fit(panel.X)
    fitted = beats_baseline(ev)
    ridge = Ridge(alpha=ev.alpha).fit(scaler.transform(panel.X), panel.y) if fitted else None
    return _Model(ridge, scaler, ev.mae, accuracy, accuracy_n, scaler.mean_, scaler.scale_,
                  fitted, len(panel), ev, leading, ratings, data_fingerprint())


# --------------------------------------------------------------------------- #
# forecast
# --------------------------------------------------------------------------- #
def _real_features(ds: Dataset, cid: str) -> Optional[list[float]]:
    """The live feature row: the most recent year whose features are ALL real. Kept under
    this name because interpret.py explains exactly this vector."""
    client = MockLLMClient()
    for year in range(config.CURRENT_YEAR, config.START_YEAR - 1, -1):
        row = _features_at(ds, cid, year, client)
        if row is not None:
            return row
    return None


def _panel(ds: Dataset, client: LLMClient):
    """(X, y, keys) for interpret.py's model card."""
    panel = _panel_rows(ds, client, horizon=0)
    return panel.X, panel.y, [f"{cid}@{year}" for cid, year in panel.keys]


def _live_year(ds: Dataset, cid: str) -> Optional[int]:
    client = MockLLMClient()
    for year in range(config.CURRENT_YEAR, config.START_YEAR - 1, -1):
        if _features_at(ds, cid, year, client) is not None:
            return year
    return None


def _label(level: Optional[float]) -> Optional[str]:
    if level is None:
        return None
    return NUM_TO_MSCI.get(int(round(min(max(level, 1), 7))))


def _last_rating(model: _Model, cid: str) -> tuple[Optional[int], Optional[int]]:
    years = model.ratings.get(cid) or {}
    if not years:
        return None, None
    latest = max(years)
    return years[latest], latest


def forecast(ds: Dataset, cid: str, model: _Model, client: Optional[LLMClient] = None) -> Forecast:
    """The company's MSCI rating as the model reads it TODAY, led by the direction.

    When the fitted model did not beat naive persistence, this returns persistence itself,
    labelled — a baseline with a stated reason, never an overfit dressed up as a model.
    """
    client = client or MockLLMClient()
    last, last_year = _last_rating(model, cid)
    feats = _real_features(ds, cid)
    year = _live_year(ds, cid)

    if last is None and (feats is None or not model.fitted):
        return Forecast(company_id=cid, predicted_score=None, hypothesis=True,
                        model_label="No real MSCI rating disclosed for this company",
                        trace=TraceNode(label="MSCI rating estimate — N.A. (no real rating)"))

    contribs: list[FeatureContribution] = []
    if model.fitted and feats is not None and model.ridge is not None:
        x = np.array(feats, float)
        xs = (x - model.means) / model.stds
        pred = float(np.clip(model.ridge.predict(xs.reshape(1, -1))[0], 1.0, 7.0))
        contribs = [FeatureContribution(feature=name, value=round(float(v), 2),
                                        contribution=round(float(coef * sx), 3))
                    for name, coef, v, sx in zip(FEATURES, model.ridge.coef_, x, xs)]
        contribs.sort(key=lambda c: -abs(c.contribution))
        label = (f"MSCI rating nowcast (Ridge on real dated signals, "
                 f"{model.rows} real rows)")
    else:
        pred = float(last)
        why = ("insufficient history for a fitted model"
               if model.rows < config.MIN_FORECAST_ROWS
               else "the fitted model did not beat it")
        label = (f"baseline: ratings persistence ({why} — {model.rows} real rows)")

    direction = _move(pred - last) if last is not None else None
    direction_text = {1: "likely upgrade", 0: "likely hold", -1: "likely downgrade",
                      None: "no prior rating to compare"}[direction]
    # On the baseline path the fitted model's numbers are NOT this prediction's numbers.
    # Advertising them would put a cross-validated accuracy on a call the model did not
    # make, so the baseline ships with no interval and no accuracy claim.
    fitted = model.fitted and bool(contribs)
    err = (model.val_error if model.val_error is not None else 0.5) if fitted else None
    accuracy = model.directional_accuracy if fitted else None
    accuracy_txt = (f", direction {round(accuracy * 100)}% of n={model.directional_n}"
                    if accuracy is not None else "")
    if year is not None:
        note = (
            f"Estimates the MSCI ESG rating as of {config.CURRENT_YEAR} from signals all "
            f"dated to {year} — GDELT headlines published that year, that year's own "
            f"report evidence, and prices to the end of it. {year} is the most recent year "
            "whose every feature is real; nothing is carried forward to fill the gap. It "
            "is not a rater publication; it is what those signals imply the rater would say."
        )
    else:
        note = (
            "No year has a complete set of real features for this company (a year needs "
            "dated news, its own extracted report and price history), so this is the last "
            "rating the company disclosed, carried as-is and labelled."
        )
    trace = TraceNode(
        label=f"{direction_text} — MSCI {_label(pred)} ({label}{accuracy_txt})",
        value=round(pred, 2),
        children=([TraceNode(label=f"last disclosed rating {_label(last)} ({last_year})",
                             value=float(last))] if last is not None else [])
        + [TraceNode(label=f"{c.feature}={c.value}", contribution=c.contribution) for c in contribs],
    )
    return Forecast(
        company_id=cid, predicted_score=round(pred, 2), horizon_years=0,
        ci_low=(round(max(1.0, pred - err), 2) if err is not None else None),
        ci_high=(round(min(7.0, pred + err), 2) if err is not None else None),
        feature_contributions=contribs,
        val_error=(round(err, 3) if err is not None else None),
        directional_accuracy=(round(accuracy, 3) if accuracy is not None else None),
        directional_n=(model.directional_n or None) if fitted else None,
        target_year=config.CURRENT_YEAR, drift_years=0, drift_note=note,
        predicted_label=_label(pred), last_rating_label=_label(last),
        last_rating_year=last_year, direction=direction_text,
        baseline_only=not model.fitted, model_label=label,
        hypothesis=True, trace=trace)


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _report(name: str, ev: Evaluation) -> str:
    def pct(v):
        return "N.A." if v is None else f"{round(v * 100)}%"

    lines = [f"{name}: n={ev.n} real rows"]
    if ev.mae is not None:
        lines.append(f"  level     MAE={ev.mae:.2f} over n={ev.n}"
                     f"  |  on the n={ev.persistence_n} rows with a prior rating: model "
                     f"{None if ev.mae_on_persistence_rows is None else round(ev.mae_on_persistence_rows, 2)}"
                     f" vs persistence {None if ev.baseline_mae_persistence is None else round(ev.baseline_mae_persistence, 2)}"
                     f"  |  panel-mean {round(ev.baseline_mae_mean, 2) if ev.baseline_mae_mean else None}")
        lines.append(f"  side      {pct(ev.side_acc)} of n={ev.side_n} "
                     f"(baseline {pct(ev.side_baseline)})")
        lines.append(f"  move      {pct(ev.move_acc)} of n={ev.move_n} "
                     f"(naive hold {pct(ev.move_baseline)})")
        lines.append(f"  luck      p={None if ev.p_value is None else round(ev.p_value, 3)} "
                     "(chance of doing this well by luck against the baseline)")
        lines.append(f"  verdict   {'BEATS' if beats_baseline(ev) else 'DOES NOT BEAT'} the naive baseline")
    for note in ev.notes:
        lines.append(f"  note      {note}")
    return "\n".join(lines)


def main() -> None:
    from . import ingest

    ds = ingest.load()
    client = MockLLMClient()
    now = _panel_rows(ds, client, horizon=0)
    lead = _panel_rows(ds, client, horizon=1)
    print("Panel rows (company @ feature year -> real MSCI level):")
    for (cid, year), target in zip(now.keys, now.y):
        print(f"  {cid:4} {year}  -> {NUM_TO_MSCI[int(target)]}")
    print()
    print(_report("NOWCAST  (features t -> rating t)", evaluate(now)))
    print()
    print(_report("LEADING  (features t -> rating t+1)", evaluate(lead)))
    print()
    print("fingerprint:", data_fingerprint())


if __name__ == "__main__":
    main()
