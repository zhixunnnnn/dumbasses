"""Bright Data Excel/CSV <-> SQLite.

The DB is the source of truth; Excel is only an interchange format. A workbook
whose sheet names match the table names (universe, rater_scores, prices, ...)
imports 1:1 with no engine change. Usage:

    python -m backend.data.import_excel path/to/bright_data.xlsx   # import
    python -m backend.data.import_excel --export sample.xlsx       # export current DB

Missing cells stay NULL (T7) — we never default-fill.
"""
from __future__ import annotations

import sys

import pandas as pd

from backend.engine import config
from backend.engine.db import TABLES, bootstrap, reset


def import_workbook(path: str) -> None:
    conn = reset()
    xl = pd.ExcelFile(path)
    imported = []
    for table in TABLES:
        if table not in xl.sheet_names:
            continue
        df = xl.parse(table)
        df = df.where(pd.notnull(df), None)  # NaN -> None (NULL), never a fabricated default
        cols = [c[0] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        df = df[[c for c in cols if c in df.columns]]
        placeholders = ",".join("?" for _ in df.columns)
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({','.join(df.columns)}) VALUES ({placeholders})",
            list(df.itertuples(index=False, name=None)),
        )
        imported.append((table, len(df)))
    conn.commit()
    conn.close()
    for t, n in imported:
        print(f"  imported {t:16s} {n:6d} rows")
    print(f"Done -> {config.DB_PATH}")


def export_workbook(path: str) -> None:
    conn = bootstrap()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for table in TABLES:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            df.to_excel(writer, sheet_name=table, index=False)
    conn.close()
    print(f"Exported current DB -> {path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "--export":
        export_workbook(args[1] if len(args) > 1 else str(config.DATA_DIR / "sample_workbook.xlsx"))
    else:
        import_workbook(args[0])
