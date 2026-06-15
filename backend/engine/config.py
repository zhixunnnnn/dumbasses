"""Paths and tunable thresholds for the engine.

Every magic number that affects a surfaced result lives here so it is auditable
(guardrail: thresholds are config, not buried constants).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ----- paths -------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency). Secrets stay git-ignored."""
    for env in (BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()
ENGINE_DIR = BACKEND_DIR / "engine"
CONFIG_DIR = ENGINE_DIR / "config"
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "esg.db"
CACHE_DIR = BACKEND_DIR / "cache"
MODELS_DIR = BACKEND_DIR / "models"
OUT_DIR = BACKEND_DIR / "out"

for _d in (DATA_DIR, CACHE_DIR, MODELS_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ----- analysis window ---------------------------------------------------------
START_YEAR = 2019
END_YEAR = 2023
YEARS = list(range(START_YEAR, END_YEAR + 1))
WINDOW_START = "2019-01-04"      # first Friday of the window
WINDOW_END = "2023-12-29"        # last Friday of the window
STI_ID = "_STI"                  # reserved company_id for the benchmark series

# ----- credit & scoring --------------------------------------------------------
CREDIT_VERIFIED = 1.0            # full credit (independently corroborated)
CREDIT_ASSERTED = 0.5           # partial credit (company-disclosed)
CREDIT_INFERRED = 0.25          # low credit (LLM estimate for an undisclosed topic — labelled)
# absence never enters the score (it only lowers confidence) — see score.py / T3

# ----- normalization -----------------------------------------------------------
MSCI_LETTER_TO_NUM = {          # higher = better
    "CCC": 1, "B": 2, "BB": 3, "BBB": 4, "A": 5, "AA": 6, "AAA": 7,
}
SUSTAINALYTICS_MAX = 100.0       # risk scale; inverted as (MAX - risk) so higher = better
MIN_PEERS_FOR_SECTOR_RANK = 5    # below this, fall back to whole-panel rank

# ----- divergence / signal -----------------------------------------------------
MIN_RATERS_FOR_DIVERGENCE = 2
HIGH_DIVERGENCE = 33.0           # percentile-point spread that counts as "raters disagree"
STALE_CONSENSUS_EPS = 5.0        # consensus moved < this over the window => "stale"
PROOF_UP_MIN_SLOPE = 1.0         # evidence-score points/year to count as improving
MIN_YEARS_FOR_MOMENTUM = 3       # below this, momentum is N.A. (not placeable on matrix)
FLAT_BAND = 10.0                 # stock-minus-STI return %: above this the market has "reacted"
QUADRANT_X_SPLIT = 50.0          # consensus-percentile midpoint: high vs low ESG "today"

# ----- forecast ----------------------------------------------------------------
FORECAST_HORIZON_YEARS = 1
TRAIN_MAX_YEAR = 2022            # time-split: train <= 2022, test == 2023
MIN_FEATURE_YEARS = 3            # below this, no forecast (N.A.)

NA = None                        # the single sentinel for "no data" — never a fabricated 0


def load_json(name: str) -> dict:
    """Load a bundled config file from engine/config/."""
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
