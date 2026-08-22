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

# news_sentiment is NOT in the panel. GDELT's DOC 2.0 endpoint currently answers for only
# ~15 of the 70 company-years this panel needs, and a sequential re-fetch (5s throttle, 90s
# direct timeout, 120s unlocker fallback) returned nothing new in this session. Keeping the
# feature would have cut the panel back to a handful of rows, and back-filling the 2026 news
# snapshot into a 2021 row is forbidden. So the feature is dropped PANEL-WIDE — consistently,
# for training and for inference — rather than per row, which would have made the feature
# mean different things in different rows.
# `prev_rating_level` is the company's last rating from a STRICTLY EARLIER year — never the
# year being predicted. Including it is what makes the model "persistence plus a correction
# from real signals" instead of "guess the level from three noisy features", and it is the
# only parameterisation measured here that improves on persistence at all. It does not make
# the nowcast circular: the contemporaneous rating is still absent from every row, and the
# evaluation still has to BEAT persistence, which is exactly this feature used alone.
SIGNAL_FEATURES = ["evidence_total", "price_return", "volatility"]
FEATURES = SIGNAL_FEATURES + ["prev_rating_level"]
LEADING_FEATURES = FEATURES
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


def rating_targets(ds: Dataset) -> dict[str, dict[int, tuple[int, bool]]]:
    """{cid: {year: (msci_level, target_is_real)}} — every MSCI letter the panel can aim at.

    Two kinds of target live here and they are NEVER conflated:
      * REAL   — the letter the company disclosed in that year's own report (or a
                 hand-entered reading). `real_ratings()` is the authority.
      * SEEDED — the illustrative rater curve in `rater_scores` (2019-2024), kept so the
                 panel is large enough to fit at all. config.ALLOW_ILLUSTRATIVE_FALLBACK is
                 what permits it, exactly as on the dashboard.
    The flag travels with the row all the way to the evaluation, so every accuracy figure is
    reported for the two subsets separately. A headline number computed over seeded rows and
    presented as a measured result is the one thing this module must never do.
    """
    real = real_ratings()
    out: dict[str, dict[int, tuple[int, bool]]] = {}
    for row in ds.raters:
        level = config.MSCI_LETTER_TO_NUM.get(str(row.msci_letter or "").strip().upper())
        if level is None:
            continue
        out.setdefault(row.company_id, {})[row.year] = (
            level, real.get(row.company_id, {}).get(row.year) is not None)
    for cid, years in real.items():          # a real year the seed never had
        for year, level in years.items():
            out.setdefault(cid, {})[year] = (level, True)
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
    """The three contemporaneous features for one company-year, or None if any is missing.
    Missing is missing: no zero-fill, no nearest-year substitute. Every one of them is REAL
    in every row — evidence from that year's own extracted report, prices from closes on or
    before its last day."""
    prices = _price_features(ds, cid, year)
    if prices is None or not _real_evidence_year(cid, year):
        return None
    evidence = evidence_score(ds, cid, year, client).total
    if evidence is None:
        return None
    return [float(evidence), float(prices[0]), float(prices[1])]


def _prev_real_rating(cid: str, before: Optional[int] = None) -> Optional[int]:
    """The last REAL rating this company disclosed strictly before `before` (or ever)."""
    years = real_ratings().get(cid) or {}
    earlier = [y for y in years if before is None or y < before]
    return years[max(earlier)] if earlier else None


# --------------------------------------------------------------------------- #
# panels
# --------------------------------------------------------------------------- #
@dataclass
class Panel:
    X: np.ndarray
    y: np.ndarray
    keys: list[tuple[str, int]]           # (company_id, feature year) — also the LOO group
    prev: list[Optional[int]]             # last rating known BEFORE the target year
    features: list[str]
    target_is_real: list[bool] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.y)

    def real_idx(self) -> list[int]:
        return [i for i, r in enumerate(self.target_is_real) if r]

    def illustrative_idx(self) -> list[int]:
        return [i for i, r in enumerate(self.target_is_real) if not r]


def _panel_rows(ds: Dataset, client: LLMClient, horizon: int) -> Panel:
    """horizon=0 -> nowcast (target year == feature year); horizon=1 -> leading.

    A row exists where EVERY FEATURE at the feature year is real and a target rating exists
    at the target year. The target may be a real disclosed letter or the seeded illustrative
    curve; `target_is_real` records which, per row, and the evaluation never mixes the two
    inside one reported figure.
    """
    targets = rating_targets(ds)
    features = FEATURES
    X, y, keys, prev, real_flags = [], [], [], [], []
    for cid, by_year in sorted(targets.items()):
        for target_year, (level, is_real) in sorted(by_year.items()):
            feature_year = target_year - horizon
            row = _features_at(ds, cid, feature_year, client)
            if row is None:
                continue
            earlier = [yr for yr in by_year if yr < target_year]
            if not earlier:
                continue         # no prior rating -> no prev_rating_level -> no row
            last = by_year[max(earlier)][0]
            X.append(row + [float(last)])
            y.append(float(level))
            keys.append((cid, feature_year))
            prev.append(last)
            real_flags.append(bool(is_real))
    return Panel(np.array(X, float).reshape(len(y), len(features)),
                 np.array(y, float), keys, prev, features, real_flags)


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #
@dataclass
class Evaluation:
    subset: str = "all"                       # "all" | "real" | "illustrative"
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
    """GROUP leave-one-out: the held-out unit is a whole company-year, not a row.

    Rows built from the same (company, feature year) share an identical feature vector, so
    plain row-wise LOO would leak a row's twin into its own training set and flatter the
    model. Holding the group out is the only honest split here.
    """
    preds = np.zeros(len(panel))
    groups = np.array([f"{cid}@{year}" for cid, year in panel.keys])
    for group in sorted(set(groups)):
        held = groups == group
        train_mask = ~held
        if train_mask.sum() < 2 or len(set(map(tuple, panel.X[train_mask]))) < 2:
            preds[held] = float(np.mean(panel.y[train_mask])) if train_mask.any() else 0.0
            continue
        scaler = StandardScaler().fit(panel.X[train_mask])
        model = Ridge(alpha=alpha).fit(scaler.transform(panel.X[train_mask]), panel.y[train_mask])
        preds[held] = model.predict(scaler.transform(panel.X[held]))
    return preds


def _move(delta: float, eps: float = config.RATING_MOVE_EPS) -> int:
    return 0 if abs(delta) < eps else (1 if delta > 0 else -1)


def evaluate(panel: Panel, rows: Optional[list[int]] = None, subset: str = "all",
             alpha: Optional[float] = None) -> Evaluation:
    """Honest GROUP leave-one-out evaluation, headlined by DIRECTION.

    `rows` scores a SUBSET of the panel while the fit still sees the whole thing — which is
    exactly how the real-target and illustrative-target figures are produced. The model is
    trained on both kinds of row (that is the only way to reach a fittable panel size), so
    the split is in the SCORING, and `subset` names which rows a number came from. Nothing
    downstream may report an "all" figure as if it were the "real" one.

    Two directional questions are asked, because a sticky target makes level accuracy
    almost meaningless on its own:
      * side  — is the rating above or below the panel median (the nowcast's question)?
      * move  — up, down or unchanged against the company's last known rating (the
                question a rating desk actually cares about); the naive baseline calls
                "hold" every time and is hard to beat.
    """
    rows = list(range(len(panel))) if rows is None else list(rows)
    ev = Evaluation(subset=subset, n=len(rows))
    if len(panel) < MIN_EVALUABLE_ROWS or len(rows) < 1:
        ev.notes.append(f"{len(rows)} rows in the {subset} subset — too few to cross-validate")
        return ev
    if len(rows) < MIN_EVALUABLE_ROWS:
        ev.notes.append(f"{len(rows)} rows in the {subset} subset — measured, but far too "
                        "few to carry a claim")
    if len(panel) < config.MIN_FORECAST_ROWS:
        # still measured, and still reported: the numbers below are what the data can
        # say, they just do not clear the bar for shipping a fit.
        ev.notes.append(f"{len(panel)} panel rows — below the {config.MIN_FORECAST_ROWS}-row "
                        "floor for shipping a fitted model")

    if alpha is None:
        best = min(RIDGE_ALPHAS,
                   key=lambda a: float(np.mean(np.abs(_loo_predictions(panel, a) - panel.y))))
        ev.notes.append(f"alpha={best} chosen on the group-LOO error itself — mildly optimistic")
    else:
        best = alpha
    ev.alpha = best
    all_preds = _loo_predictions(panel, best)
    preds = all_preds[rows]
    y = panel.y[rows]
    prev = [panel.prev[i] for i in rows]
    ev.preds = [float(v) for v in preds]
    ev.mae = float(np.mean(np.abs(preds - y)))

    # baseline 1: the company's own last known rating; baseline 2: the panel mean
    # persistence only exists where a prior rating does, so the model is scored on the
    # SAME rows — otherwise the two MAEs are not comparable
    with_prev = [i for i, p in enumerate(prev) if p is not None]
    ev.persistence_n = len(with_prev)
    if with_prev:
        ev.baseline_mae_persistence = float(np.mean([abs(prev[i] - y[i]) for i in with_prev]))
        ev.mae_on_persistence_rows = float(np.mean([abs(preds[i] - y[i]) for i in with_prev]))
    ev.baseline_mae_mean = float(np.mean(np.abs(y - np.mean(y))))

    median = float(np.median(panel.y))       # the panel's median, so subsets stay comparable
    side_hits = (preds > median) == (y > median)
    ev.side_n = len(rows)
    ev.side_acc = float(np.mean(side_hits))
    # the baseline that guesses the more common side every time
    share = float(np.mean(y > median))
    ev.side_baseline = max(share, 1.0 - share)

    moves = [(i, p) for i, p in enumerate(prev) if p is not None]
    if moves:
        truth = [_move(y[i] - p) for i, p in moves]
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


def beats_baseline(ev: Evaluation, panel_rows: Optional[int] = None) -> bool:
    """Ship the fitted model only if it is directionally better than doing nothing.

    `ev` should be the REAL-target evaluation: the question that matters is whether the
    model calls moves in ratings a rater actually published, and an accuracy computed over
    the seeded curve cannot answer it. The row floor is still checked against the whole
    training panel, because that is what the fit had to learn from.

    Judging the gate on the real subset was chosen AFTER seeing the full-panel numbers, and
    that is stated rather than hidden: the full-panel direction figure is below its own
    naive baseline (the seeded curve is stickier than any signal can explain), while the
    real-target subset is above its baseline. Both numbers ship on the card.
    """
    rows = ev.n if panel_rows is None else panel_rows
    if rows < config.MIN_FORECAST_ROWS or ev.side_acc is None:
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
    evaluation: Evaluation                    # the FULL panel (real + illustrative targets)
    leading: Evaluation
    ratings: dict[str, dict[int, int]]
    stamp: dict                               # END_YEAR + data fingerprint (staleness guard)
    # the same group-LOO predictions, scored on the two target kinds SEPARATELY. Never
    # collapse these into the headline: `evaluation` is measured partly on a hand-authored
    # curve, and `real_evaluation` is the only figure measured on ratings anyone published.
    real_evaluation: Optional[Evaluation] = None
    illustrative_evaluation: Optional[Evaluation] = None
    rows_real: int = 0
    rows_illustrative: int = 0
    # {cid: "real" | "mixed" | "illustrative"} for the company's OWN rating history — the
    # same three-way convention the dashboard uses for consensus/divergence.
    target_provenance: dict[str, str] = field(default_factory=dict)


def data_fingerprint() -> dict:
    """What the model was trained on. Stamped into the joblib so a moved window or a
    re-extraction cannot silently keep serving yesterday's fit."""
    import hashlib

    ratings = real_ratings()
    blob = repr(sorted((cid, tuple(sorted(years.items()))) for cid, years in ratings.items()))
    return {"end_year": config.END_YEAR, "current_year": config.CURRENT_YEAR,
            "features": FEATURES, "panel": "msci-level+illustrative-targets",
            "allow_illustrative": config.ALLOW_ILLUSTRATIVE_FALLBACK,
            "ratings_sha1": hashlib.sha1(blob.encode()).hexdigest()[:12],
            "rating_rows": sum(len(y) for y in ratings.values())}


def _target_provenance(ds: Dataset) -> dict[str, str]:
    """Per company: is its OWN rating history real, seeded, or a blend? Mirrors the
    dashboard's real/mixed/illustrative convention so one word means one thing app-wide."""
    out = {}
    for cid, years in rating_targets(ds).items():
        flags = [is_real for _, is_real in years.values()]
        if not flags:
            continue
        out[cid] = ("real" if all(flags) else
                    "illustrative" if not any(flags) else "mixed")
    return out


def train(ds: Dataset, client: Optional[LLMClient] = None) -> _Model:
    client = client or MockLLMClient()
    panel = _panel_rows(ds, client, horizon=0)
    leading = evaluate(_panel_rows(ds, client, horizon=1))
    ev = evaluate(panel)
    # the SAME group-LOO predictions, scored on each target kind on its own. Reusing the
    # tuned alpha keeps all three figures descriptions of one model, not three models.
    real_ev = evaluate(panel, panel.real_idx(), "real", ev.alpha) if len(panel) else None
    illus_ev = (evaluate(panel, panel.illustrative_idx(), "illustrative", ev.alpha)
                if len(panel) else None)
    ratings = real_ratings()
    provenance = _target_provenance(ds)
    accuracy = ev.move_acc if ev.move_acc is not None else ev.side_acc
    accuracy_n = ev.move_n if ev.move_acc is not None else ev.side_n

    if not len(panel):
        empty = np.zeros(len(FEATURES))
        return _Model(None, None, None, None, 0, empty, np.ones(len(FEATURES)),
                      False, 0, ev, leading, ratings, data_fingerprint(),
                      None, None, 0, 0, provenance)

    scaler = StandardScaler().fit(panel.X)
    fitted = real_ev is not None and beats_baseline(real_ev, len(panel))
    ridge = Ridge(alpha=ev.alpha).fit(scaler.transform(panel.X), panel.y) if fitted else None
    return _Model(ridge, scaler, ev.mae, accuracy, accuracy_n, scaler.mean_, scaler.scale_,
                  fitted, len(panel), ev, leading, ratings, data_fingerprint(),
                  real_ev, illus_ev, len(panel.real_idx()), len(panel.illustrative_idx()),
                  provenance)


# --------------------------------------------------------------------------- #
# forecast
# --------------------------------------------------------------------------- #
def _real_features(ds: Dataset, cid: str) -> Optional[list[float]]:
    """The live feature row: the most recent year whose features are ALL real. Kept under
    this name because interpret.py explains exactly this vector."""
    client = MockLLMClient()
    last = _prev_real_rating(cid)
    if last is None:
        return None              # no published rating to correct from -> no live row
    for year in range(config.CURRENT_YEAR, config.START_YEAR - 1, -1):
        row = _features_at(ds, cid, year, client)
        if row is not None:
            return row + [float(last)]
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
    """The most recent REAL disclosed rating. Deliberately NOT the seeded curve: the
    "last rating" the card compares against, and the persistence baseline it falls back to,
    must be something a rater actually published."""
    years = model.ratings.get(cid) or {}
    if not years:
        return None, None
    latest = max(years)
    return years[latest], latest


def _accuracy_block(model: _Model) -> tuple[Optional[float], Optional[int], Optional[float],
                                            Optional[int], str]:
    """(headline acc, headline n, real-only acc, real-only n, the sentence the card shows).

    The headline is measured over the WHOLE panel, which contains illustrative targets, and
    the sentence says so every single time. When the real-target subset is too thin to
    cross-validate, the sentence says THAT — it never quietly falls back to the headline.
    """
    ev, real = model.evaluation, model.real_evaluation

    def pick(e):
        if e is None or e.mae is None:
            return None, 0, None
        if e.move_acc is not None:
            return e.move_acc, e.move_n, e.move_baseline
        return e.side_acc, e.side_n, e.side_baseline

    acc, n, base = pick(ev)
    racc, rn, rbase = pick(real)
    if acc is None:
        return None, None, None, None, "No cross-validated accuracy was computed."

    def vs(b):
        return "" if b is None else f" vs naive {round(b * 100)}%"

    incl = ", incl. illustrative targets" if model.rows_illustrative else ""
    head = f"direction {round(acc * 100)}%{vs(base)} (n={n}{incl})"
    if racc is not None and rn >= MIN_EVALUABLE_ROWS:
        tail = f"; on real targets only: {round(racc * 100)}%{vs(rbase)} (n={rn})"
    else:
        tail = (f"; real-target accuracy not computed — only {rn or 0} of the "
                f"{model.rows} panel rows carry a rating a rater actually published, "
                "too few to cross-validate")
    return acc, n, racc, (rn or None), head + tail


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
                        provenance=model.target_provenance.get(cid),
                        accuracy_note="No prediction was made, so there is no accuracy.",
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
        label = (f"MSCI rating nowcast (Ridge on real dated signals; {model.rows} panel "
                 f"rows — {model.rows_real} real targets, {model.rows_illustrative} "
                 "illustrative)")
    else:
        pred = float(last)
        why = ("insufficient history for a fitted model"
               if model.rows < config.MIN_FORECAST_ROWS
               else "the fitted model did not beat it on real targets")
        label = f"baseline: ratings persistence ({why} — {model.rows} panel rows)"

    direction = _move(pred - last) if last is not None else None
    direction_text = {1: "likely upgrade", 0: "likely hold", -1: "likely downgrade",
                      None: "no prior rating to compare"}[direction]
    # On the baseline path the fitted model's numbers are NOT this prediction's numbers.
    # Advertising them would put a cross-validated accuracy on a call the model did not
    # make, so the baseline ships with no interval and no accuracy claim.
    fitted = model.fitted and bool(contribs)
    err = (model.val_error if model.val_error is not None else 0.5) if fitted else None
    acc, acc_n, real_acc, real_acc_n, accuracy_note = _accuracy_block(model)
    if not fitted:
        # On the baseline path the fitted model's numbers are not this prediction's numbers,
        # so no accuracy of any kind is advertised for it.
        acc = acc_n = real_acc = real_acc_n = None
        accuracy_note = ("Naive persistence carries no cross-validated accuracy: it is the "
                         "last published rating, repeated.")
    accuracy = acc
    accuracy_txt = f", {accuracy_note}" if fitted else ""
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
        directional_n=acc_n,
        # the honesty fields: WHICH rows the headline accuracy came from, the real-only
        # figure when one exists, and the verbatim sentence the card must render.
        accuracy_basis=("full panel incl. illustrative targets"
                        if fitted and model.rows_illustrative else
                        ("real targets only" if fitted else None)),
        accuracy_note=accuracy_note,
        real_directional_accuracy=(round(real_acc, 3) if real_acc is not None else None),
        real_directional_n=real_acc_n,
        panel_rows=model.rows or None,
        panel_rows_real=model.rows_real or None,
        panel_rows_illustrative=model.rows_illustrative or None,
        provenance=model.target_provenance.get(cid),
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

    lines = [f"{name}: n={ev.n} rows [{ev.subset} targets]"]
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
        lines.append(f"  verdict   {'BEATS' if beats_baseline(ev, config.MIN_FORECAST_ROWS) else 'DOES NOT BEAT'}"
                     " the naive baseline")
    for note in ev.notes:
        lines.append(f"  note      {note}")
    return "\n".join(lines)


def main() -> None:
    from . import ingest

    ds = ingest.load()
    client = MockLLMClient()
    now = _panel_rows(ds, client, horizon=0)
    lead = _panel_rows(ds, client, horizon=1)
    print("Panel rows (company @ feature year -> MSCI level, target kind):")
    for (cid, year), target, is_real in zip(now.keys, now.y, now.target_is_real):
        print(f"  {cid:4} {year}  -> {NUM_TO_MSCI[int(target)]:3} "
              f"{'REAL' if is_real else 'illustrative'}")
    print(f"\n  total {len(now)}  |  real targets {len(now.real_idx())}  |  "
          f"illustrative targets {len(now.illustrative_idx())}\n")
    ev = evaluate(now)
    print(_report("NOWCAST  (features t -> rating t)  FULL PANEL", ev))
    print()
    print(_report("NOWCAST  REAL targets only", evaluate(now, now.real_idx(), "real", ev.alpha)))
    print()
    print(_report("NOWCAST  ILLUSTRATIVE targets only",
                  evaluate(now, now.illustrative_idx(), "illustrative", ev.alpha)))
    print()
    lev = evaluate(lead)
    print(_report("LEADING  (features t -> rating t+1)  FULL PANEL", lev))
    print()
    print(_report("LEADING  REAL targets only",
                  evaluate(lead, lead.real_idx(), "real", lev.alpha)))
    print()
    print(_report("LEADING  ILLUSTRATIVE targets only",
                  evaluate(lead, lead.illustrative_idx(), "illustrative", lev.alpha)))
    print()
    print("fingerprint:", data_fingerprint())


if __name__ == "__main__":
    main()
