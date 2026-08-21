"""Paths and tunable thresholds for the engine.

Every magic number that affects a surfaced result lives here so it is auditable
(guardrail: thresholds are config, not buried constants).
"""
from __future__ import annotations

import json
import os
import shutil
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
RUNTIME_DATA_DIR = Path(
    os.environ.get("POLYFINTECH_DATA_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or DATA_DIR
).expanduser()
DB_PATH = RUNTIME_DATA_DIR / "esg.db"
CACHE_DIR = BACKEND_DIR / "cache"
MODELS_DIR = BACKEND_DIR / "models"
OUT_DIR = BACKEND_DIR / "out"

for _d in (RUNTIME_DATA_DIR, CACHE_DIR, MODELS_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# A fresh Railway volume starts empty. Seed it from the committed database once,
# then let subsequent writes remain on the persistent volume.
_BUNDLED_DB_PATH = DATA_DIR / "esg.db"
if DB_PATH != _BUNDLED_DB_PATH and not DB_PATH.exists() and _BUNDLED_DB_PATH.exists():
    shutil.copy2(_BUNDLED_DB_PATH, DB_PATH)

# ----- analysis window ---------------------------------------------------------
START_YEAR = 2019
END_YEAR = 2024                  # latest year with real, year-verified reports for 9/10 names
                                 # (2025 reaches only 5/10 — FY2025 disclosures are not out yet)
YEARS = list(range(START_YEAR, END_YEAR + 1))
WINDOW_START = "2019-01-04"      # first Friday of the window
WINDOW_END = "2024-12-27"        # last Friday of the window
STI_ID = "_STI"                  # reserved company_id for the benchmark series
CURRENT_YEAR = 2026              # live estimate is presented as a real-time nowcast for this year
PRICE_END_YEAR = 2026            # prices/Price Witness run to today; evidence stays at END_YEAR (report lag)

# ----- report reading ----------------------------------------------------------
# Claim extraction reads the first ~64k chars of a report (realclaims.REPORT_CHARS); that
# is enough for the material topics but NOT for rating disclosures, which live on an
# awards/ratings page deep inside the PDF. Rating extraction therefore reads the whole
# document — one fetch, no LLM cost per extra page.
RATINGS_REPORT_CHARS = 600000

# ----- credit & scoring --------------------------------------------------------
CREDIT_VERIFIED = 1.0            # full credit (independently corroborated)
CREDIT_ASSERTED = 0.5           # partial credit (company-disclosed)
CREDIT_INFERRED = 0.25          # low credit (LLM estimate for an undisclosed topic — labelled)
# A topic's credit is capped by its BEST evidence tier, so mere disclosure can't
# reach full marks: only an independently VERIFIED topic can hit 1.0. This keeps
# perfect pillar scores (100) rare and meaningful.
ASSERTED_TOPIC_CAP = 0.7        # asserted-only topic tops out here (high, but not full)
# absence never enters the score (it only lowers confidence) — see score.py / T3

# ----- normalization -----------------------------------------------------------
MSCI_LETTER_TO_NUM = {          # higher = better
    "CCC": 1, "B": 2, "BB": 3, "BBB": 4, "A": 5, "AA": 6, "AAA": 7,
}
SUSTAINALYTICS_MAX = 100.0       # risk scale; inverted as (MAX - risk) so higher = better
SP_GLOBAL_MAX = 100.0            # S&P Global ESG Score, already higher = better
CDP_LETTER_TO_NUM = {           # CDP climate-change score, higher = better
    "D-": 1, "D": 2, "C-": 3, "C": 4, "B-": 5, "B": 6, "A-": 7, "A": 8,
}
MIN_PEERS_FOR_SECTOR_RANK = 5    # below this, fall back to whole-panel rank; below it there
                                 # too, the rank is noise and the percentile is N.A.

# ----- divergence / signal -----------------------------------------------------
MIN_RATERS_FOR_DIVERGENCE = 2
# ...and at least this many of them must be REAL ratings (scraped, or hand-entered with
# provenance via engine/manual_raters.py). A spread between one real rating and an
# illustrative one measures the seed, not what raters disagree about, so consensus and
# divergence are N.A. below this floor rather than plausibly wrong.
# How many REAL ratings a figure needs before it may be shown WITHOUT an illustrative
# fallback. In strict mode this is a hard gate (below it -> N.A.); with the fallback on it
# is the floor for earning the "real" provenance label.
MIN_REAL_RATERS_FOR_DIVERGENCE = 2
# Prototype default: where we have no real rating, fall back to the illustrative (seeded)
# value rather than showing N.A. everywhere. This is NOT silent fabrication — every
# derived figure ships a provenance label ("real" | "mixed" | "illustrative") saying which
# channels actually contributed, so a viewer can never mistake a seeded number for a
# measured one. Flip to False to restore strict real-only mode: consensus, divergence and
# thin industry medians become N.A. instead of falling back.
ALLOW_ILLUSTRATIVE_FALLBACK = True
# KnowESG (data/realraters.py) stopped publishing numeric scores, so its cached MSCI
# letters can no longer be re-fetched, re-dated or checked. They still overlay the seed —
# a real letter beats an invented one — but they do NOT count towards the floor above.
# Flip to True only if that source becomes reproducible again.
TRUST_SCRAPED_RATERS_AS_REAL = False
HIGH_DIVERGENCE = 25.0           # percentile-point spread that counts as "raters disagree" (loosened for demo)
STALE_CONSENSUS_EPS = 8.0        # consensus moved < this over the window => "stale" (loosened for demo)
PROOF_UP_MIN_SLOPE = 0.5         # evidence-score points/year to count as improving (loosened for demo)
MIN_YEARS_FOR_MOMENTUM = 3       # below this, momentum is N.A. (not placeable on matrix)
FLAT_BAND = 15.0                 # stock-minus-STI return %: above this the market has "reacted" (loosened for demo)
QUADRANT_X_SPLIT = 50.0          # consensus-percentile midpoint: high vs low ESG "today"

# ----- satellite verification --------------------------------------------------
# Open, keyless services: OSM Overpass for asset coordinates, Element84 Earth Search
# (STAC over AWS public Sentinel-2 L2A) for dated scenes, TiTiler to render a bbox.
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
STAC_SEARCH_URL = os.environ.get("STAC_SEARCH_URL", "https://earth-search.aws.element84.com/v1/search")
STAC_ITEM_URL = os.environ.get(
    "STAC_ITEM_URL", "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items")
TITILER_URL = os.environ.get("TITILER_URL", "https://titiler.xyz")

SAT_MAX_CLOUD = 15.0             # reject scenes cloudier than this (tropical SEA is cloudy)
SAT_BBOX_HALF_DEG = 0.013        # fallback half-width (~1.4 km) when there is no outline
SAT_BBOX_PAD = 0.6               # pad the footprint by this fraction to leave a control area
SAT_BBOX_MIN_HALF = 0.004        # floor on that padding, for very small assets
SAT_EDGE_BUFFER = 0.02           # frame fraction excluded either side of the outline
SAT_IMAGE_PX = 640               # rendered tile edge, px
SAT_RESCALE = "0,3000"           # Sentinel-2 L2A reflectance stretch for true colour
# Detection is a difference-in-differences on a spectral index: how far the index moved
# ON the asset, minus how far it moved in the surrounding control area. The control leg
# cancels season, sun angle and regional drift, which a raw brightness delta cannot.
SAT_BAND_RESCALE = "0,4000"      # shared linear stretch, so band ratios stay valid
SAT_MIN_SITE_DELTA = 0.10        # the asset itself must move this much, or it is UNCHANGED
                                 # (a big DiD driven purely by the NEIGHBOURS changing is
                                 # not construction here)
SAT_DID_CHANGED = 0.15           # |DiD| at or above this = CHANGED
SAT_DID_UNCHANGED = 0.05         # |DiD| at or below this = UNCHANGED; between = inconclusive
SAT_MIN_MATCH_CONF = 0.5         # ignore registry rows we cannot tie firmly to the company

# High-resolution basemap for the "see it yourself" view. Esri World Imagery is sub-metre
# in most places and needs no key, but carries no reliable capture date — so it illustrates,
# it never decides a verdict. Attribution is mandatory and ships with the payload.
BASEMAP_TILE_URL = os.environ.get(
    "BASEMAP_TILE_URL",
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
BASEMAP_TARGET_PX = 2200         # pixel budget for the stitched render
BASEMAP_MAX_ZOOM = 19
BASEMAP_MAX_TILES = 120          # refuse absurd stitches rather than hammer the tile server
BASEMAP_JPEG_QUALITY = 82        # aerial photography; PNG would be ~10x the bytes
BASEMAP_OUTPUT_MAX_PX = 1400     # cap the delivered image; six cards ship together

# ----- forecast ----------------------------------------------------------------
FORECAST_HORIZON_YEARS = 1       # the leading model's horizon: rating at t+1
# Below this many REAL panel rows nothing is fitted: the forecast falls back to naive
# ratings persistence and says so, rather than overfitting a handful of observations.
MIN_FORECAST_ROWS = 15
# A rating "move" on the MSCI 1..7 scale. Predictions are continuous, so a call only
# counts as an upgrade/downgrade once it crosses half a notch.
RATING_MOVE_EPS = 0.5

NA = None                        # the single sentinel for "no data" — never a fabricated 0


def load_json(name: str) -> dict:
    """Load a bundled config file from engine/config/."""
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
