"""Read the SQLite store into typed objects. The engine consumes these — never raw SQL."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from . import config
from .db import bootstrap
from .models import Candle, Company


@dataclass
class RaterRow:
    company_id: str
    year: int
    msci_letter: Optional[str]
    sustainalytics_risk: Optional[float]
    sp_global: Optional[float]


@dataclass
class DocumentRow:
    company_id: str
    doc_id: str
    title: str
    year: int
    url: Optional[str]
    source_page: Optional[int]
    text: str


@dataclass
class EvidenceRow:
    evidence_id: str
    company_id: str
    domain: str
    authority_source: str
    snippet: str
    url: Optional[str]
    supports: bool
    date: Optional[str]
    topic_id: Optional[str]


@dataclass
class EventRow:
    company_id: str
    date: str
    type: str
    label: str
    value: Optional[float]


@dataclass
class RegulationRow:
    reg_id: str
    jurisdiction: str
    name: str
    scope: str
    requirement: str
    effective_year: int


@dataclass
class RegComplianceRow:
    company_id: str
    reg_id: str
    year: int
    status: Optional[str]
    evidence_ref: Optional[str]


@dataclass
class Dataset:
    companies: dict[str, Company]
    raters: list[RaterRow]
    prices: dict[str, list[Candle]]
    fundamentals: dict[str, dict]
    documents: list[DocumentRow]
    evidence: list[EvidenceRow]
    events: list[EventRow]
    regulations: list[RegulationRow]
    reg_compliance: list[RegComplianceRow]
    news_sentiment: dict[str, int] = field(default_factory=dict)   # live Bright Data signal

    # ---- convenience accessors -------------------------------------------------
    def demo_ids(self) -> list[str]:
        return [c.company_id for c in self.companies.values() if c.scope == "demo"]

    def company(self, cid: str) -> Company:
        return self.companies[cid]

    def raters_for(self, cid: str) -> list[RaterRow]:
        return [r for r in self.raters if r.company_id == cid]

    def docs_for(self, cid: str, year: Optional[int] = None) -> list[DocumentRow]:
        return [d for d in self.documents if d.company_id == cid and (year is None or d.year == year)]

    def evidence_for(self, cid: str, domain: Optional[str] = None, year: Optional[int] = None) -> list[EvidenceRow]:
        out = [e for e in self.evidence if e.company_id == cid]
        if domain is not None:
            out = [e for e in out if e.domain == domain]
        if year is not None:
            out = [e for e in out if (e.date or "").startswith(str(year))]
        return out

    def events_for(self, cid: str) -> list[EventRow]:
        return [e for e in self.events if e.company_id == cid]

    def compliance_for(self, cid: str) -> list[RegComplianceRow]:
        return [r for r in self.reg_compliance if r.company_id == cid]


def load(db_path=None) -> Dataset:
    conn = bootstrap(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row

    companies = {
        r["company_id"]: Company(
            company_id=r["company_id"], ticker=r["ticker"], name=r["name"], country=r["country"],
            exchange=r["exchange"], sector=r["sector"], sasb_industry=r["sasb_industry"],
            scope=r["scope"] or "reference",
        )
        for r in conn.execute("SELECT * FROM universe")
    }
    raters = [RaterRow(r["company_id"], r["year"], r["msci_letter"], r["sustainalytics_risk"], r["sp_global"])
              for r in conn.execute("SELECT * FROM rater_scores")]

    prices: dict[str, list[Candle]] = {}
    for r in conn.execute("SELECT * FROM prices ORDER BY company_id, week_date"):
        prices.setdefault(r["company_id"], []).append(
            Candle(week_date=r["week_date"], open=r["open"], high=r["high"],
                   low=r["low"], close=r["close"], volume=r["volume"]))

    fundamentals: dict[str, dict] = {}
    for r in conn.execute("SELECT * FROM fundamentals"):
        fundamentals.setdefault(r["company_id"], {})[r["period"]] = {"pe": r["pe"], "dividend_yield": r["dividend_yield"]}

    documents = [DocumentRow(r["company_id"], r["doc_id"], r["title"], r["year"], r["url"], r["source_page"], r["text"])
                 for r in conn.execute("SELECT * FROM documents")]
    evidence = [EvidenceRow(r["evidence_id"], r["company_id"], r["domain"], r["authority_source"], r["snippet"],
                            r["url"], bool(r["supports"]), r["date"], r["topic_id"])
                for r in conn.execute("SELECT * FROM evidence")]
    events = [EventRow(r["company_id"], r["date"], r["type"], r["label"], r["value"])
              for r in conn.execute("SELECT * FROM events")]
    regulations = [RegulationRow(r["reg_id"], r["jurisdiction"], r["name"], r["scope"], r["requirement"], r["effective_year"])
                   for r in conn.execute("SELECT * FROM regulations")]
    reg_compliance = [RegComplianceRow(r["company_id"], r["reg_id"], r["year"], r["status"], r["evidence_ref"])
                      for r in conn.execute("SELECT * FROM reg_compliance")]
    news_sentiment = {r["company_id"]: (r["sentiment"] or 0)
                      for r in conn.execute("SELECT company_id, sentiment FROM news")}
    conn.close()

    return Dataset(companies, raters, prices, fundamentals, documents, evidence, events,
                   regulations, reg_compliance, news_sentiment)
