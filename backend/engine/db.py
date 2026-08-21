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

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- live ESG research provenance and source-quality decisions -----------------
CREATE TABLE IF NOT EXISTS source_registry (
    domain          TEXT PRIMARY KEY,
    source_class    TEXT NOT NULL CHECK (source_class IN ('verified','non_verified','community')),
    reason          TEXT,
    is_builtin      INTEGER NOT NULL DEFAULT 0,
    -- a builtin cannot be deleted (initialize would re-add it); it is disabled instead
    is_disabled     INTEGER NOT NULL DEFAULT 0,
    -- once edited by hand, the builtin seed no longer overwrites reason/class
    user_modified   INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_promotion_candidates (
    domain                    TEXT PRIMARY KEY,
    status                    TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    overlap_score             REAL NOT NULL DEFAULT 0,
    matching_claims           INTEGER NOT NULL DEFAULT 0,
    matched_verified_domains  TEXT NOT NULL DEFAULT '[]',
    first_seen                TEXT NOT NULL,
    last_seen                 TEXT NOT NULL,
    reviewed_at               TEXT
);

CREATE TABLE IF NOT EXISTS research_runs (
    run_id          TEXT PRIMARY KEY,
    scope           TEXT NOT NULL,
    company_id      TEXT,
    status          TEXT NOT NULL,
    providers_json  TEXT NOT NULL DEFAULT '[]',
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    source_count    INTEGER NOT NULL DEFAULT 0,
    claim_count     INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    message         TEXT
);

CREATE TABLE IF NOT EXISTS research_claims (
    claim_id        TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL,
    claim_text      TEXT NOT NULL,
    topic           TEXT NOT NULL,
    verification    TEXT NOT NULL CHECK (verification IN ('verified','non_verified','community')),
    sentiment       REAL NOT NULL DEFAULT 0,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_claim_sources (
    claim_id        TEXT NOT NULL,
    canonical_url   TEXT NOT NULL,
    domain          TEXT NOT NULL,
    source_class    TEXT NOT NULL,
    title           TEXT,
    snippet         TEXT,
    provider        TEXT,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (claim_id, canonical_url)
);

CREATE TABLE IF NOT EXISTS scraped_pages (
    url_hash        TEXT PRIMARY KEY,
    canonical_url   TEXT NOT NULL,
    domain          TEXT NOT NULL,
    provider        TEXT,
    title           TEXT,
    extracted_text  TEXT,
    source_class    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS renewable_status (
    company_id           TEXT PRIMARY KEY,
    renewable_status     TEXT NOT NULL,
    emissions_trend      TEXT NOT NULL,
    evidence_count       INTEGER NOT NULL DEFAULT 0,
    verified_count       INTEGER NOT NULL DEFAULT 0,
    latest_evidence_at   TEXT,
    updated_at           TEXT NOT NULL
);

-- scraped regulation provenance (a real source link/excerpt per regime) -------
CREATE TABLE IF NOT EXISTS reg_source (
    reg_id         TEXT PRIMARY KEY,
    source_url     TEXT,
    source_excerpt TEXT,
    fetched_at     TEXT
);

-- scraped, CURRENT per-company compliance proof (layered over the seed; the
-- engine prefers this when present). status MISSING is only set when an
-- authoritative document was actually retrieved and the disclosure was absent;
-- if no document could be retrieved the status is NULL (UNKNOWN -> excluded).
CREATE TABLE IF NOT EXISTS reg_evidence (
    company_id     TEXT,
    reg_id         TEXT,
    status         TEXT,        -- MET | PARTIAL | MISSING | NULL(unknown)
    matched        INTEGER,     -- # of disclosure keywords found
    source_url     TEXT,
    source_excerpt TEXT,
    fetched_at     TEXT,
    source         TEXT,
    PRIMARY KEY (company_id, reg_id)
);

-- cached Monday-morning manager briefing, one row per company per SG calendar
-- day (regenerated lazily on first request each day; see engine/briefing.py)
CREATE TABLE IF NOT EXISTS company_briefings (
    company_id        TEXT,
    briefing_date      TEXT,    -- YYYY-MM-DD, Asia/Singapore
    headline           TEXT,
    summary            TEXT,
    potential_effects  TEXT,    -- JSON array of strings
    watch_items        TEXT,    -- JSON array of strings
    sentiment          TEXT,    -- positive | neutral | negative | mixed
    generated_at       TEXT,
    PRIMARY KEY (company_id, briefing_date)
);

-- cached portfolio-level rollup of the Monday briefing, one row per SG
-- calendar day (paired with company_briefings above)
CREATE TABLE IF NOT EXISTS briefing_overview (
    briefing_date  TEXT PRIMARY KEY,
    headline       TEXT,
    summary        TEXT,
    watch_items    TEXT,    -- JSON array of strings
    generated_at   TEXT
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


# columns added after the first release; SCHEMA only covers freshly created DBs
MIGRATIONS = (
    ("source_registry", "is_disabled", "INTEGER NOT NULL DEFAULT 0"),
    ("source_registry", "user_modified", "INTEGER NOT NULL DEFAULT 0"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns missing from an existing database. Idempotent."""
    for table, column, definition in MIGRATIONS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def bootstrap(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the schema if absent and return an open connection."""
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
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
