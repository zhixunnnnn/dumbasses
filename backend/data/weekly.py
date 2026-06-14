"""Weekly Monday refresh — investors act on Monday morning, so the signals refresh weekly.

Scraped data is persisted in the DB; between refreshes we serve from the DB and never
re-scrape. A refresh runs only if the last successful run was >= 7 days ago.

    python -m backend.data.weekly            # run once now if stale (else use DB)
    python -m backend.data.weekly --force    # refresh now regardless
    python -m backend.data.weekly --daemon   # blocking scheduler: every Monday 06:00

In the FastAPI app the same job is scheduled in-process (see app/main.py); for production
use Windows Task Scheduler / cron to call `python -m backend.data.weekly` every Monday.
"""
from __future__ import annotations

import argparse
import datetime as dt
from typing import Optional

from backend.engine import brightdata
from backend.engine.db import bootstrap
from backend.data.scrape import scrape_news

REFRESH_DAYS = 7


def last_run(conn, source: str = "news") -> Optional[str]:
    row = conn.execute("SELECT last_run FROM scrape_log WHERE source=?", (source,)).fetchone()
    return row["last_run"] if row else None


def should_refresh(conn, source: str = "news", days: int = REFRESH_DAYS) -> bool:
    last = last_run(conn, source)
    if not last:
        return True
    try:
        return (dt.datetime.utcnow() - dt.datetime.fromisoformat(last)).days >= days
    except ValueError:
        return True


def run_weekly(force: bool = False, offline: bool = False) -> None:
    conn = bootstrap()
    try:
        if not offline and not brightdata.browser_available() and not brightdata.available():
            print("weekly: no Bright Data credentials — serving existing DB snapshot.")
            return
        if not force and not should_refresh(conn):
            print(f"weekly: news is fresh (last {last_run(conn)}) — using DB, no re-scrape.")
            return
        print("weekly: refreshing live signals via Bright Data…")
        scrape_news(conn, offline=offline)
    except Exception as exc:  # noqa: BLE001 — a scheduled refresh must never crash the app
        print(f"weekly: refresh failed ({type(exc).__name__}: {str(exc)[:100]}); keeping last snapshot.")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--daemon", action="store_true", help="block and run every Monday 06:00")
    args = ap.parse_args()
    if args.daemon:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        sched = BlockingScheduler()
        sched.add_job(lambda: run_weekly(force=True), CronTrigger(day_of_week="mon", hour=6))
        print("weekly daemon started — refreshing every Monday 06:00. Ctrl+C to stop.")
        run_weekly()  # catch-up on start
        sched.start()
    else:
        run_weekly(force=args.force, offline=args.offline)


if __name__ == "__main__":
    main()
