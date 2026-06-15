"""Deterministic seed builder for the demo.

Produces a coherent, reproducible `esg.db` so the whole pipeline + dashboard run
fully offline. Seed *data* is illustrative (clearly labelled in the README); the
*engine* logic is identical on real Bright Data / yfinance inputs. Re-run with:

    python -m backend.data.seed

NOTE: numbers are synthetic but plausible and intentionally tell a story
(Sembcorp = Hidden Winner: rising verified evidence under a flat price, raters
disagreeing). Real data drops in via data/import_excel.py with no engine change.
"""
from __future__ import annotations

import datetime as dt
import json
import random

from backend.engine import config
from backend.engine.db import reset


# ---------------------------------------------------------------------------
# time axis
# ---------------------------------------------------------------------------
def weekly_fridays() -> list[str]:
    start = dt.date.fromisoformat(config.WINDOW_START)
    end = dt.date.fromisoformat(config.WINDOW_END)
    out, d = [], start
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=7)
    return out


FRIDAYS = weekly_fridays()


def gen_prices(rng: random.Random, start: float, annual_drift: float, annual_vol: float):
    """Geometric weekly walk -> OHLC candles. drift/vol are annualised."""
    wk_drift = annual_drift / 52.0
    wk_vol = annual_vol / (52 ** 0.5)
    price = start
    rows = []
    for fri in FRIDAYS:
        ret = rng.gauss(wk_drift, wk_vol)
        close = max(0.05, price * (1 + ret))
        op = price
        hi = max(op, close) * (1 + abs(rng.gauss(0, wk_vol / 2)))
        lo = min(op, close) * (1 - abs(rng.gauss(0, wk_vol / 2)))
        rows.append({"week_date": fri, "open": round(op, 3), "high": round(hi, 3),
                     "low": round(lo, 3), "close": round(close, 3),
                     "volume": round(rng.uniform(1e6, 9e6))})
        price = close
    return rows


# ---------------------------------------------------------------------------
# claim phrasing (verbatim source sentences; contain keywords for SASB mapping)
# ---------------------------------------------------------------------------
TOPIC_PHRASES = {
    "financed_emissions": "expanded sustainable financing and set interim financed emissions targets toward net zero",
    "business_ethics": "strengthened its anti-corruption code of conduct and board ethics oversight",
    "data_security": "invested in cybersecurity controls to prevent customer data breach incidents",
    "systemic_risk": "maintained capital adequacy well above regulatory minimums under stress test scenarios",
    "financial_inclusion": "broadened financial inclusion programmes for underserved SME customers",
    "employee_diversity": "increased gender diversity with more women in leadership roles",
    "energy_management": "improved energy efficiency across its green building portfolio",
    "ghg_emissions": "reduced Scope 1 and Scope 2 carbon emissions intensity",
    "climate_resilience": "published TCFD-aligned climate risk and physical resilience assessments",
    "water_management": "lowered water intensity through recycled water initiatives",
    "tenant_sustainability": "rolled out green lease and tenant wellbeing engagement programmes",
    "energy_transition": "grew its renewables and solar capacity as part of its decarbonisation transition",
    "workforce_safety": "reduced lost-time injuries through occupational health and safety programmes",
    "air_quality": "cut NOx and particulate air quality emissions at its plants",
    "grid_resiliency": "improved grid reliability and supply security",
    "fuel_efficiency": "improved fuel efficiency through fleet renewal and lower fuel burn",
    "labor_relations": "advanced collective labour relations and crew engagement",
    "safety_management": "enhanced its safety management system and incident reporting",
    "land_use_deforestation": "committed to a no-deforestation, no-peat, no-exploitation (NDPE) land use policy",
    "supply_chain_traceability": "improved supply chain traceability with RSPO-certified and audited suppliers",
    "food_safety": "upheld food safety and product quality standards",
    "workforce_health_safety": "protected worker safety and labour rights across operations",
    "data_privacy_security": "reinforced data privacy and cybersecurity for customer data",
    "product_access": "expanded digital inclusion and affordable connectivity access",
    "competitive_behavior": "maintained fair competition and pricing practices",
    "workforce_diversity": "invested in workforce diversity and digital reskilling",
    "workforce": "invested in workforce safety, diversity and training",
    "resource_use": "improved energy, water and waste circularity",
    "data_governance": "strengthened data governance, cyber and privacy risk management",
}


def claim_sentence(name: str, year: int, topic_id: str) -> str:
    return f"In FY{year}, {name} {TOPIC_PHRASES[topic_id]}."


# ---------------------------------------------------------------------------
# demo universe (10 SGX large caps) with story parameters
#   vf = per-year verified fraction (2019..2023) controlling the evidence trajectory
#   absent = topic_ids deliberately left undisclosed (material -> ABSENT, lowers confidence only)
#   raters = (msci letters per yr, sustainalytics risk per yr, sp per yr); None = N.A.
# ---------------------------------------------------------------------------
MSCI_BY = {"low": "BBB", "mid": "A", "high": "AA", "top": "AAA", "weak": "BB", "poor": "B"}

DEMO = [
    {
        "id": "U96", "ticker": "U96.SI", "name": "Sembcorp Industries", "country": "Singapore",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.10, 0.18, 0.30, 0.45, 0.58], "absent": [],
        "price": (3.2, 0.02, 0.30),  # start, annual_drift (flat-ish), vol
        # raters STUCK LOW and FLAT while verified evidence climbs -> the gap the market hasn't priced
        "msci": ["B", "B", "B", "B", "B"],
        "sust": [44, 44, 44, 44, 44], "sp": [34, 34, 34, 34, 34],
        "story": "HERO Hidden Winner: verified renewables transition rising, price flat, raters lagging.",
    },
    {
        "id": "BN4", "ticker": "BN4.SI", "name": "Keppel Ltd", "country": "Singapore",
        "sector": "Industrials", "industry": "Electric Utilities & Power Generators",
        "vf": [0.20, 0.28, 0.40, 0.52, 0.62], "absent": [],
        "price": (5.5, 0.04, 0.28),
        # raters STUCK (stale consensus) and low while verified evidence climbs -> underpriced
        "msci": ["BB", "BB", "BB", "BB", "BB"],
        "sust": [38, 38, 38, 38, 38], "sp": [42, 42, 42, 42, 42],
        "story": "Hidden Winner: O&M -> green infra; verified evidence ahead of the raters.",
    },
    {
        "id": "F34", "ticker": "F34.SI", "name": "Wilmar International", "country": "Singapore",
        "sector": "Consumer Staples", "industry": "Agricultural Products",
        "vf": [0.45, 0.40, 0.35, 0.30, 0.28], "absent": ["land_use_deforestation"],
        "price": (4.2, -0.03, 0.30),
        # DIVERGENT raters (controversial name -> Trust Meter demo): MSCI low, Sustainalytics
        # comparatively kind, S&P low -> wide spread
        "msci": ["BBB", "BB", "BB", "B", "B"],
        "sust": [18, 19, 20, 21, 22], "sp": [42, 40, 39, 38, 37],
        "controversy_year": 2021,
        "story": "Value Trap: declining evidence, deforestation controversy, raters split.",
    },
    {
        "id": "C6L", "ticker": "C6L.SI", "name": "Singapore Airlines", "country": "Singapore",
        "sector": "Industrials", "industry": "Airlines",
        "vf": [0.30, 0.28, 0.35, 0.45, 0.52], "absent": [],
        "price": (9.0, -0.02, 0.32),
        "msci": ["BBB", "BBB", "BBB", "A", "A"],
        "sust": [30, 29, 28, 27, 26], "sp": [52, 54, 56, 58, 60],
        "story": "Improver: SAF / climate claims verified over time.",
    },
    {
        "id": "D05", "ticker": "D05.SI", "name": "DBS Group", "country": "Singapore",
        "sector": "Financials", "industry": "Commercial Banks",
        "vf": [0.62, 0.66, 0.70, 0.74, 0.78], "absent": [],
        "price": (25.0, 0.06, 0.22),
        "msci": ["A", "AA", "AA", "AA", "AA"],
        "sust": [22, 20, 18, 17, 16], "sp": [70, 73, 76, 78, 80],
        "story": "Consensus leader: high score, raters agree (low divergence).",
    },
    {
        "id": "O39", "ticker": "O39.SI", "name": "OCBC", "country": "Singapore",
        "sector": "Financials", "industry": "Commercial Banks",
        "vf": [0.58, 0.60, 0.64, 0.68, 0.70], "absent": [],
        "price": (11.0, 0.04, 0.22),
        "msci": ["A", "A", "AA", "AA", "AA"],
        "sust": [24, 22, 20, 19, 18], "sp": [66, 69, 72, 74, 76],
        "story": "Leader.",
    },
    {
        "id": "U11", "ticker": "U11.SI", "name": "UOB", "country": "Singapore",
        "sector": "Financials", "industry": "Commercial Banks",
        "vf": [0.55, 0.57, 0.60, 0.63, 0.66], "absent": [],
        "price": (26.0, 0.03, 0.22),
        "msci": ["A", "A", "A", "AA", "AA"],
        "sust": [26, 24, 22, 21, 20], "sp": [62, 65, 68, 70, 72],
        "story": "Leader.",
    },
    {
        "id": "9CI", "ticker": "9CI.SI", "name": "CapitaLand Investment", "country": "Singapore",
        "sector": "Real Estate", "industry": "Real Estate",
        "vf": [0.60, 0.66, 0.72, 0.78, 0.84], "absent": [],
        "price": (3.6, 0.05, 0.24),
        "msci": ["AA", "AA", "AAA", "AAA", "AAA"],
        "sust": [16, 15, 14, 13, 12], "sp": [80, 82, 84, 86, 88],
        "story": "Future Leader: high score and still improving.",
    },
    {
        "id": "C09", "ticker": "C09.SI", "name": "City Developments", "country": "Singapore",
        "sector": "Real Estate", "industry": "Real Estate",
        "vf": [0.82, 0.80, 0.78, 0.75, 0.72], "absent": [],
        "price": (8.5, -0.04, 0.26),
        # raters still HIGH (market pays a premium) while evidence quietly deteriorates
        "msci": ["AAA", "AAA", "AAA", "AA", "AA"],
        "sust": [12, 12, 13, 13, 14], "sp": [88, 88, 87, 86, 85],
        "story": "Overrated Leader: high score but deteriorating; market still pays premium.",
    },
    {
        "id": "Z74", "ticker": "Z74.SI", "name": "Singtel", "country": "Singapore",
        "sector": "Telecoms", "industry": "Telecommunication Services",
        "vf": [0.48, 0.50, 0.54, 0.58, 0.62], "absent": [],
        "price": (3.3, 0.01, 0.24),
        "msci": ["A", "A", "A", "AA", "AA"],
        "sust": [26, 25, 24, 23, 22], "sp": [60, 62, 64, 66, 68],
        "story": "Mid-pack improver; digital-transformation angle.",
    },
]

# reference panel (ASEAN) — background only: rater coverage + ML rows.
REF_SECTORS = [
    ("Commercial Banks", "Financials"), ("Real Estate", "Real Estate"),
    ("Electric Utilities & Power Generators", "Utilities"), ("Airlines", "Industrials"),
    ("Agricultural Products", "Consumer Staples"), ("Telecommunication Services", "Telecoms"),
    ("Default", "Industrials"), ("Default", "Materials"),
]
REF_COUNTRIES = ["Singapore", "Malaysia", "Indonesia", "Thailand", "Philippines", "Vietnam"]
REF_EXCHANGES = {"Singapore": "SGX", "Malaysia": "Bursa", "Indonesia": "IDX",
                 "Thailand": "SET", "Philippines": "PSE", "Vietnam": "HOSE"}


def build():
    conn = reset()
    rng = random.Random(20260614)

    regs = json.loads((config.CONFIG_DIR / "regulations.json").read_text("utf-8"))["regulations"]
    _insert_regulations(conn, regs)

    # STI benchmark series (reserved company_id) — modest positive market drift
    for row in gen_prices(rng, 3200.0, 0.035, 0.16):
        conn.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                     (config.STI_ID, row["week_date"], row["open"], row["high"],
                      row["low"], row["close"], row["volume"]))

    for c in DEMO:
        _insert_company(conn, c, scope="demo")
        _insert_demo_rows(conn, c, rng, regs)

    # reference panel
    n = 0
    for si, (industry, sector) in enumerate(REF_SECTORS):
        for k in range(6):
            n += 1
            country = REF_COUNTRIES[(si + k) % len(REF_COUNTRIES)]
            cid = f"REF{n:03d}"
            comp = {
                "id": cid, "ticker": f"{cid}", "name": f"{industry.split()[0]} ASEAN {n}",
                "country": country, "exchange": REF_EXCHANGES[country],
                "sector": sector, "industry": industry,
            }
            _insert_company(conn, comp, scope="reference", exchange=comp["exchange"])
            _insert_reference_rows(conn, comp, rng)

    conn.commit()
    _summary(conn)
    conn.close()


def _insert_regulations(conn, regs):
    for r in regs:
        conn.execute(
            "INSERT OR REPLACE INTO regulations VALUES (?,?,?,?,?,?)",
            (r["reg_id"], r["jurisdiction"], r["name"], r["scope"], r["requirement"], r["effective_year"]),
        )


def _insert_company(conn, c, scope, exchange="SGX"):
    conn.execute(
        "INSERT OR REPLACE INTO universe VALUES (?,?,?,?,?,?,?,?)",
        (c["id"], c["ticker"], c["name"], c["country"], c.get("exchange", exchange),
         c["sector"], c["industry"], scope),
    )


def _materiality_topics(industry: str):
    mat = config.load_json("sasb_materiality.json")
    block = mat.get(industry) or mat["Default"]
    return block["topics"]


def _insert_demo_rows(conn, c, rng, regs):
    name, cid, industry = c["name"], c["id"], c["industry"]
    topics = sorted(_materiality_topics(industry), key=lambda t: -t["weight"])
    present_topics = [t for t in topics if t["topic_id"] not in c["absent"]]

    # rater scores + prices + fundamentals
    for i, year in enumerate(config.YEARS):
        conn.execute(
            "INSERT OR REPLACE INTO rater_scores VALUES (?,?,?,?,?)",
            (cid, year, c["msci"][i], float(c["sust"][i]), float(c["sp"][i])),
        )
    start, drift, vol = c["price"]
    for row in gen_prices(rng, start, drift, vol):
        conn.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                     (cid, row["week_date"], row["open"], row["high"], row["low"], row["close"], row["volume"]))
    conn.execute("INSERT OR REPLACE INTO fundamentals VALUES (?,?,?,?)",
                 (cid, "2023", round(rng.uniform(8, 22), 1), round(rng.uniform(2, 5), 2)))

    # documents + evidence per year, with verified fraction controlling the trajectory
    for i, year in enumerate(config.YEARS):
        vf = c["vf"][i]
        n_present = len(present_topics)
        n_verified = round(vf * n_present)
        text_sentences = []
        for j, t in enumerate(present_topics):
            sent = claim_sentence(name, year, t["topic_id"])
            text_sentences.append(sent)
            verified = j < n_verified
            if verified:
                _add_evidence(conn, cid, t, year, supports=1)
        # controversy: a contradicting evidence row + event (Wilmar)
        if c.get("controversy_year") == year:
            _add_evidence(conn, cid, present_topics[-1], year, supports=0,
                          authority="controversies", snippet="NGO report alleges deforestation in supply chain")
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                         (cid, f"{year}-09-15", "controversy", "Deforestation controversy (NGO report)", None))
        doc_text = " ".join(text_sentences)
        conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)",
                     (cid, f"{cid}-SR{year}", f"{name} Sustainability Report {year}", year,
                      f"https://example.com/{cid}/sr{year}.pdf", 1, doc_text))

        # hiring surge event for improvers (leading signal)
        if c["vf"][-1] - c["vf"][0] > 0.2 and year in (2021, 2022):
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                         (cid, f"{year}-06-30", "hiring_surge",
                          f"Sustainability hiring surge ({year})", float(rng.randint(8, 30))))

    # reg_compliance per applicable reg/year (inferred-style statuses)
    _insert_compliance(conn, c, regs)


def _add_evidence(conn, cid, topic, year, supports, authority=None, snippet=None):
    domain = topic["domain"]
    auth_map = {"climate": "CDP", "governance": "regulator", "supply_chain": "EcoVadis", "labour": "regulator_penalties"}
    authority = authority or auth_map.get(domain, "regulator")
    snippet = snippet or f"{authority} record corroborating {topic['topic_id']} ({year})"
    eid = f"{cid}-{topic['topic_id']}-{year}-{supports}"
    conn.execute("INSERT OR REPLACE INTO evidence VALUES (?,?,?,?,?,?,?,?,?)",
                 (eid, cid, domain, authority, snippet,
                  f"https://example.com/evidence/{eid}", supports, f"{year}-12-31", topic["topic_id"]))
    if domain == "climate" and supports == 1:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                     (cid, f"{year}-12-31", "emissions_verified",
                      f"Emissions verified by {authority} ({year})", None))


def _insert_compliance(conn, c, regs):
    cid = c["id"]
    is_fi = c["industry"] == "Commercial Banks"
    is_sgx = c["country"] == "Singapore"
    sector = c["sector"]
    for year in config.YEARS:
        for r in regs:
            # applicability gate (sector targeting > scope) + effective year
            sectors = r.get("applies_to_sectors") or []
            if sectors:
                if sector not in sectors:
                    continue
            elif r["scope"] == "MAS-FI" and not is_fi:
                continue
            elif r["scope"].startswith("SGX") and not is_sgx:
                continue
            if year < r["effective_year"]:
                status = "NA"           # not in force yet -> readiness gap, never violation
            else:
                # demo: leaders MET, improvers PARTIAL->MET, laggard MISSING on some
                vf = c["vf"][config.YEARS.index(year)]
                if r["reg_id"] == "SGX-711B":
                    status = "MET"
                elif vf >= 0.6:
                    status = "MET"
                elif vf >= 0.35:
                    status = "PARTIAL"
                else:
                    status = "MISSING"
            conn.execute("INSERT OR REPLACE INTO reg_compliance VALUES (?,?,?,?,?)",
                         (cid, r["reg_id"], year, status, f"{cid}-SR{year}"))


def _insert_reference_rows(conn, c, rng):
    """Reference panel: STABLE rater profiles (ratings rarely swing year-to-year), some NULL
    for coverage gaps, + a single latest-year evidence proxy via documents."""
    cid, industry, name = c["id"], c["industry"], c["name"]
    base = rng.uniform(0.3, 0.85)
    letters = ["B", "BB", "BBB", "A", "AA", "AAA"]
    msci0 = rng.choice(letters) if rng.random() > 0.12 else None
    sust0 = rng.uniform(14, 48) if rng.random() > 0.18 else None
    sp0 = rng.uniform(36, 86) if rng.random() > 0.22 else None
    for k, year in enumerate(config.YEARS):
        msci = msci0  # rating held constant across the window
        sust = round(sust0 - k * rng.uniform(0.0, 0.4), 1) if sust0 is not None else None
        sp = round(sp0 + k * rng.uniform(0.0, 0.4), 1) if sp0 is not None else None
        conn.execute("INSERT OR REPLACE INTO rater_scores VALUES (?,?,?,?,?)",
                     (cid, year, msci, sust, sp))
    # latest-year document only (reference exists for ranking/ML, not detail pages)
    topics = sorted(_materiality_topics(industry), key=lambda t: -t["weight"])
    n_verified = round(base * len(topics))
    sentences = []
    for j, t in enumerate(topics):
        sentences.append(claim_sentence(name, config.END_YEAR, t["topic_id"]))
        if j < n_verified:
            _add_evidence(conn, cid, t, config.END_YEAR, supports=1)
    conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)",
                 (cid, f"{cid}-SR{config.END_YEAR}", f"{name} SR {config.END_YEAR}",
                  config.END_YEAR, f"https://example.com/{cid}.pdf", 1, " ".join(sentences)))


def _summary(conn):
    for t in ("universe", "rater_scores", "prices", "documents", "evidence", "events", "reg_compliance"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {n:6d} rows")


if __name__ == "__main__":
    print("Building seed esg.db ...")
    build()
    print(f"Done -> {config.DB_PATH}")
