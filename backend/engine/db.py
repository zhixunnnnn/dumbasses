"""SQLite source-of-truth: schema bootstrap + connection helpers.

The DB is the canonical store; Excel/CSV is only an import format (see
data/import_excel.py). Missing values are stored as NULL — never default-filled (T7).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS universe (
    company_id    TEXT PRIMARY KEY,
    ticker        TEXT,
    name          TEXT,
    country       TEXT,
    exchange      TEXT,
    sector        TEXT,
    sasb_industry TEXT,
    scope         TEXT CHECK (scope IN ('demo','reference')) DEFAULT 'reference'
);

CREATE TABLE IF NOT EXISTS rater_scores (
    company_id          TEXT,
    year                INTEGER,
    msci_letter         TEXT,
    sustainalytics_risk REAL,    -- LOWER = better (inverted in normalize.py)
    sp_global           REAL,    -- 0..100 higher = better
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS prices (
    company_id TEXT,
    week_date  TEXT,             -- ISO Friday
    open       REAL,
    high       REAL,
    low        REAL,
    close      REAL,
    volume     REAL,
    PRIMARY KEY (company_id, week_date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    company_id     TEXT,
    period         TEXT,
    pe             REAL,
    dividend_yield REAL,
    PRIMARY KEY (company_id, period)
);

CREATE TABLE IF NOT EXISTS documents (
    company_id  TEXT,
    doc_id      TEXT,
    title       TEXT,
    year        INTEGER,
    url         TEXT,
    source_page INTEGER,
    text        TEXT,
    PRIMARY KEY (doc_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id      TEXT PRIMARY KEY,
    company_id       TEXT,
    domain           TEXT,       -- climate | governance | supply_chain | labour
    authority_source TEXT,
    snippet          TEXT,
    url              TEXT,
    supports         INTEGER,    -- 1 supports, 0 contradicts
    date             TEXT,
    topic_id         TEXT        -- optional: ties evidence to a SASB topic
);

CREATE TABLE IF NOT EXISTS events (
    company_id TEXT,
    date       TEXT,
    type       TEXT,             -- emissions_verified | hiring_surge | rater_unchanged | controversy
    label      TEXT,
    value      REAL              -- e.g. hiring count
);

CREATE TABLE IF NOT EXISTS regulations (
    reg_id         TEXT PRIMARY KEY,
    jurisdiction   TEXT,
    name           TEXT,
    scope          TEXT,         -- who it binds (e.g. 'SGX-listed')
    requirement    TEXT,
    effective_year INTEGER
);

CREATE TABLE IF NOT EXISTS reg_compliance (
    company_id   TEXT,
    reg_id       TEXT,
    year         INTEGER,
    status       TEXT,           -- MET | PARTIAL | MISSING | NA (NULL = unknown)
    evidence_ref TEXT,
    PRIMARY KEY (company_id, reg_id, year)
);

-- live alternative data (scraped via Bright Data, refreshed weekly) ----------
CREATE TABLE IF NOT EXISTS news (
    company_id  TEXT PRIMARY KEY,
    fetched_at  TEXT,
    n_items     INTEGER,
    controversy INTEGER,
    positive    INTEGER,
    sentiment   INTEGER
);

CREATE TABLE IF NOT EXISTS news_headlines (
    company_id TEXT,
    fetched_at TEXT,
    title      TEXT,
    url        TEXT,
    label      TEXT
);

CREATE TABLE IF NOT EXISTS scrape_log (
    source      TEXT PRIMARY KEY,
    last_run    TEXT,
    last_status TEXT,
    rows        INTEGER
);
"""

TABLES = [
    "universe", "rater_scores", "prices", "fundamentals", "documents",
    "evidence", "events", "regulations", "reg_compliance",
]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def bootstrap(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the schema if absent and return an open connection."""
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def reset(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Drop and recreate all tables (used when re-importing a fresh workbook)."""
    conn = connect(db_path)
    for t in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
