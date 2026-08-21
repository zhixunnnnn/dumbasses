"""Typed contracts for the engine (pydantic v2).

These mirror the build-spec §4 contracts. `None` is the only "no data" value
(guardrail T7 — never fabricate). Every surfaced number carries a `trace`.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Pillar = Literal["E", "S", "G"]
VerifyState = Literal["VERIFIED", "ASSERTED", "ABSENT"]
QuadrantKey = Literal["HIDDEN_WINNERS", "FUTURE_LEADERS", "VALUE_TRAPS", "OVERRATED"]
Quality = Literal["MET", "PARTIAL", "MISSING", "NA"]
# Where a derived number came from. "mixed" is the interesting one: it is what produced
# Keppel's misleading 87.8 divergence (a real MSCI letter spliced onto a seeded S&P), so
# it is never collapsed into a boolean.
Provenance = Literal["real", "mixed", "illustrative"]


# --- the trace spine -----------------------------------------------------------
class TraceNode(BaseModel):
    label: str
    value: Optional[float] = None
    contribution: Optional[float] = None
    source_sentence: Optional[str] = None
    source_doc: Optional[str] = None
    source_page: Optional[int] = None
    children: list["TraceNode"] = Field(default_factory=list)


# --- universe ------------------------------------------------------------------
class Company(BaseModel):
    company_id: str
    ticker: str
    name: str
    country: str
    exchange: str
    sector: str
    sasb_industry: str
    scope: Literal["demo", "reference"] = "reference"


# --- claims / verification -----------------------------------------------------
class Claim(BaseModel):
    id: str
    company_id: str
    year: int
    text: str
    source_doc: str
    source_page: Optional[int] = None
    source_sentence: str           # invariant: non-empty, verbatim


class SASBMapping(BaseModel):
    claim_id: str
    topic_id: str
    pillar: Pillar
    is_material: bool
    weight: float
    domain: str = "governance"        # routes verification authority


class EvidenceRef(BaseModel):
    authority_source: str
    snippet: str
    url: Optional[str] = None
    supports: bool


class Verification(BaseModel):
    claim_id: str
    state: Literal["VERIFIED", "ASSERTED"]   # ABSENT is topic-level (derived in score.py)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float
    authority_source: Optional[str] = None
    controversy: bool = False                # contradicted -> ASSERTED + controversy event


# --- satellite site verification -----------------------------------------------
class AssetSite(BaseModel):
    """A physical asset located in an open registry. Coordinates are NEVER inferred
    by the model — they come from a registry row we can cite (guardrail T7)."""
    site_id: str
    company_id: str
    name: Optional[str] = None
    asset_type: Optional[str] = None          # wind | solar | coal | gas | battery | waste ...
    lat: float
    lon: float
    operator: Optional[str] = None            # verbatim registry tag that matched
    registry: str = "openstreetmap"
    registry_url: Optional[str] = None        # citable permalink to the registry row
    match_confidence: float = 0.0             # how firmly this site ties to the company
    footprint: list[list[float]] = Field(default_factory=list)   # [[lat, lon], ...] outline


class SiteScene(BaseModel):
    """One dated satellite acquisition. `date` is the real capture date, not a request date."""
    scene_id: str
    date: str
    cloud_cover: Optional[float] = None
    image_path: Optional[str] = None          # relative to OUT_DIR, served by the API


class SiteObservation(BaseModel):
    """A before/after look at one site. `changed=None` means INCONCLUSIVE and is the
    default: no imagery, too much cloud, or an ambiguous metric never becomes a verdict."""
    site: AssetSite
    before: Optional[SiteScene] = None
    after: Optional[SiteScene] = None
    index: Optional[str] = None                # which spectral index carried the signal
    change_score: Optional[float] = None       # difference-in-differences on that index
    changed: Optional[bool] = None             # True | False | None (inconclusive)
    note: str = ""                             # plain-English disclosure for the UI


# --- scores --------------------------------------------------------------------
class EvidenceScore(BaseModel):
    company_id: str
    year: int
    total: Optional[float] = None            # 0..100, None if no covered material topics
    pillars: dict[str, Optional[float]] = Field(default_factory=dict)
    confidence: float = 0.0
    absent_topics: list[str] = Field(default_factory=list)
    trace: TraceNode


class RaterPercentiles(BaseModel):
    company_id: str
    msci_pct: Optional[float] = None
    sp_pct: Optional[float] = None
    sustainalytics_pct: Optional[float] = None   # already inverted -> higher = better
    cdp_pct: Optional[float] = None              # CDP climate score, real-only (no seed)
    # which channels carry a REAL rating (hand-entered or scraped); the rest are
    # illustrative seed. Derived at normalization time — never hand-maintained here.
    real_raters: list[str] = Field(default_factory=list)   # subset of RATER_KEYS
    basis: Optional[str] = None      # cohort these percentiles were ranked against
    peers: Optional[int] = None      # size of that cohort (a rank over 2 names is noise)

    def contributing(self) -> list[str]:
        """Channels that feed consensus/divergence under the current policy."""
        from . import config

        keys = [k for k, v in self._by_key().items() if v is not None]
        if config.ALLOW_ILLUSTRATIVE_FALLBACK:
            return keys
        return [k for k in keys if k in self.real_raters]

    def provenance(self) -> Optional[Provenance]:
        """Label the contributing set: all real -> "real", none real -> "illustrative",
        any blend -> "mixed". Composition decides it, so a mean of one REAL rating is
        honestly "real" (thin, but not part-invented) — thinness is carried by `peers`
        and by MIN_RATERS_FOR_DIVERGENCE, not by mislabelling provenance."""
        contributing = self.contributing()
        if not contributing:
            return None          # no number was produced, so there is nothing to label
        real = [k for k in contributing if k in self.real_raters]
        if not real:
            return "illustrative"
        return "real" if len(real) == len(contributing) else "mixed"

    def _by_key(self) -> dict[str, Optional[float]]:
        return {"msci": self.msci_pct, "sp": self.sp_pct,
                "sustainalytics": self.sustainalytics_pct, "cdp": self.cdp_pct}

    def available(self) -> list[float]:
        return [p for p in self._by_key().values() if p is not None]

    def real_available(self) -> list[float]:
        """Only the percentiles backed by a real rating."""
        return [v for k, v in self._by_key().items() if k in self.real_raters and v is not None]

    def contributing_values(self) -> list[float]:
        """The percentiles consensus/divergence actually operate on."""
        by_key = self._by_key()
        return [by_key[k] for k in self.contributing()]


# --- regulations ---------------------------------------------------------------
class RegStatus(BaseModel):
    reg_id: str
    name: str
    status: Quality
    evidence_ref: Optional[str] = None
    source_url: Optional[str] = None        # scraped proof link (when verified live)
    source_excerpt: Optional[str] = None    # verbatim sentence from the source
    scraped: bool = False                   # True = backed by live scraped evidence


class ComplianceGap(BaseModel):
    company_id: str
    score: Optional[float] = None            # fraction MISSING of in-force applicable, None if none in force
    # "real" when every counted regulation carries live scraped proof, "mixed" when some
    # do, "illustrative" when the tally rests entirely on the seeded compliance rows.
    provenance: Optional[Provenance] = None
    scraped_count: int = 0                   # how many counted rows are live-proofed
    counted: int = 0                         # how many regulations the ratio is over
    met: list[RegStatus] = Field(default_factory=list)
    partial: list[RegStatus] = Field(default_factory=list)
    missing: list[RegStatus] = Field(default_factory=list)
    not_in_force: list[RegStatus] = Field(default_factory=list)
    trace: TraceNode


# --- signal --------------------------------------------------------------------
class Signal(BaseModel):
    company_id: str
    proof_up: Optional[bool] = None
    opinion_flat: Optional[bool] = None
    price_flat: Optional[bool] = None
    is_underpriced_improver: bool = False
    evidence_pct: Optional[float] = None     # evidence rank vs companies on the SAME rubric
    evidence_basis: Optional[str] = None     # what evidence_pct is relative to (industry/sector/panel)
    evidence_peers: Optional[int] = None     # size of that cohort (a percentile over 2 names is noise)
    evidence_gap: Optional[float] = None
    momentum: Optional[float] = None         # slope of yearly evidence series
    esg_today: Optional[float] = None
    quadrant: Optional[QuadrantKey] = None
    # Every rater-derived figure inherits the consensus provenance, because consensus is
    # what they are built from. Surfaced per figure so the UI never has to infer it.
    esg_today_provenance: Optional[Provenance] = None
    evidence_gap_provenance: Optional[Provenance] = None
    quadrant_provenance: Optional[Provenance] = None
    trace: TraceNode


# --- forecast (always HYPOTHESIS) ---------------------------------------------
class FeatureContribution(BaseModel):
    feature: str
    value: Optional[float] = None
    contribution: float


class Forecast(BaseModel):
    company_id: str
    predicted_score: Optional[float] = None
    horizon_years: int = 1
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    feature_contributions: list[FeatureContribution] = Field(default_factory=list)
    val_error: Optional[float] = None        # honest test-set MAE
    directional_accuracy: Optional[float] = None  # LOO-CV: % of up/down calls correct
    directional_n: Optional[int] = None      # how many rows that accuracy was measured on
    predicted_label: Optional[str] = None    # the rating letter the level maps to
    last_rating_label: Optional[str] = None  # last REAL disclosed rating, for the comparison
    last_rating_year: Optional[int] = None
    direction: Optional[str] = None          # "likely upgrade" | "likely hold" | ...
    baseline_only: bool = False              # True -> this is naive persistence, not a fit
    model_label: Optional[str] = None        # what produced the number, verbatim for the UI
    target_year: Optional[int] = None        # year this estimate is projected to
    drift_years: Optional[int] = None        # years beyond the model's training window
    drift_note: Optional[str] = None         # plain-English drift disclosure for the UI
    hypothesis: bool = True
    trace: TraceNode


# --- price witness -------------------------------------------------------------
class Candle(BaseModel):
    week_date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class BandSpan(BaseModel):
    start_date: str
    end_date: str
    slope: float                              # evidence-score points/year over the span
    start_score: float
    end_score: float


class WitnessPin(BaseModel):
    date: str
    type: Literal["emissions_verified", "hiring_surge", "rater_unchanged", "controversy"]
    label: str
    trace_ref: TraceNode


class WitnessFlat(BaseModel):
    stock_return: Optional[float] = None
    sti_return: Optional[float] = None
    rel_return: Optional[float] = None
    is_flat: Optional[bool] = None


class Witness(BaseModel):
    company_id: str
    candles: list[Candle] = Field(default_factory=list)
    band: list[BandSpan] = Field(default_factory=list)
    pins: list[WitnessPin] = Field(default_factory=list)
    benchmark: list[Candle] = Field(default_factory=list)
    flat: WitnessFlat = Field(default_factory=WitnessFlat)


TraceNode.model_rebuild()
