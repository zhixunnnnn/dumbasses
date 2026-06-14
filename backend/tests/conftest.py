"""Shared test helpers: build small in-memory Datasets without touching the DB."""
from __future__ import annotations

from backend.engine.ingest import (
    Dataset, DocumentRow, EvidenceRow, EventRow, RaterRow, RegComplianceRow, RegulationRow,
)
from backend.engine.models import Company


def make_company(cid, sector="Banks", industry="Commercial Banks", scope="demo", country="Singapore"):
    return Company(company_id=cid, ticker=cid, name=cid, country=country, exchange="SGX",
                   sector=sector, sasb_industry=industry, scope=scope)


def make_dataset(companies=None, raters=None, prices=None, fundamentals=None, documents=None,
                 evidence=None, events=None, regulations=None, reg_compliance=None) -> Dataset:
    comp_map = {c.company_id: c for c in (companies or [])}
    return Dataset(
        companies=comp_map,
        raters=raters or [],
        prices=prices or {},
        fundamentals=fundamentals or {},
        documents=documents or [],
        evidence=evidence or [],
        events=events or [],
        regulations=regulations or [],
        reg_compliance=reg_compliance or [],
    )


__all__ = ["make_company", "make_dataset", "RaterRow", "DocumentRow", "EvidenceRow",
           "EventRow", "RegulationRow", "RegComplianceRow"]
