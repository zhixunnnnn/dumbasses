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

    def available(self) -> list[float]:
        return [p for p in (self.msci_pct, self.sp_pct, self.sustainalytics_pct) if p is not None]


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
    evidence_gap: Optional[float] = None
    momentum: Optional[float] = None         # slope of yearly evidence series
    esg_today: Optional[float] = None
    quadrant: Optional[QuadrantKey] = None
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
