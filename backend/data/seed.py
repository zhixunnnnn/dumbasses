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
# demo universe (10 ASEAN utilities) with story parameters
#   vf = per-year verified fraction (2019..2023) controlling the evidence trajectory
#   absent = topic_ids deliberately left undisclosed (material -> ABSENT, lowers confidence only)
#   raters = (msci letters per yr, sustainalytics risk per yr, sp per yr); None = N.A.
# ---------------------------------------------------------------------------
MSCI_BY = {"low": "BBB", "mid": "A", "high": "AA", "top": "AAA", "weak": "BB", "poor": "B"}

# The DEMO trajectories below were authored for a 5-year window. When config.END_YEAR
# moves, the extra years are generated by CONTINUING each authored story rather than
# repeating its last value: a flat series stays flat, a rising one keeps rising by its own
# last step, a plateaued rating holds.
#
# These rows are ILLUSTRATIVE BY CONSTRUCTION. They are seeded data, they never enter any
# real-rater cache, and RaterPercentiles.provenance() therefore reports them as
# "illustrative" wherever they surface. That is the whole basis on which extending them is
# honest: we are widening a labelled demo dataset to cover the analysis window.
#
# This is NOT carry-forward of a measurement. A REAL observation is only ever attached to
# the year it was actually measured in (see data/realratings.py and realcdp.py), and
# normalize.normalize_raters still returns N.A. for a year with no row -- extending the
# SEED must never be confused with propagating a real value into a year it was not
# observed in.
MSCI_LADDER = ["CCC", "B", "BB", "BBB", "A", "AA", "AAA"]


def extend_numeric(values, n, lo, hi):
    """Continue a numeric trajectory to n points using its own last step, clamped."""
    out = [float(v) for v in values]
    if len(out) >= n:
        return out[:n]
    step = (out[-1] - out[-2]) if len(out) >= 2 else 0.0
    whole = all(float(v).is_integer() for v in out)
    while len(out) < n:
        nxt = min(hi, max(lo, out[-1] + step))
        out.append(float(round(nxt)) if whole else round(nxt, 2))
    return out


def extend_letters(values, n):
    """Continue a rating ladder to n points. Ratings move at most one rung a year, and a
    trajectory that has already plateaued stays put."""
    out = list(values)
    if len(out) >= n:
        return out[:n]
    idx = MSCI_LADDER.index(out[-1])
    step = 0
    if len(out) >= 2 and out[-2] in MSCI_LADDER:
        step = max(-1, min(1, idx - MSCI_LADDER.index(out[-2])))
    while len(out) < n:
        idx = max(0, min(len(MSCI_LADDER) - 1, idx + step))
        out.append(MSCI_LADDER[idx])
    return out


def demo_series(c):
    """(msci, sust, sp, vf) for a DEMO company, extended to cover every config.YEARS."""
    n = len(config.YEARS)
    sp = c.get("sp")
    return (
        extend_letters(c["msci"], n),
        extend_numeric(c["sust"], n, 0.0, config.SUSTAINALYTICS_MAX),
        # A channel with no obtainable public score stays None for every year rather than
        # being seeded — a missing rater must read N.A., never as a number.
        ([None] * n if sp is None else extend_numeric(sp, n, 0.0, config.SP_GLOBAL_MAX)),
        extend_numeric(c["vf"], n, 0.0, 1.0),
    )


DEMO = [
    {
        "id": "U96", "ticker": "U96.SI", "name": "Sembcorp Industries", "country": "Singapore",
        "exchange": "SGX", "domain": "sembcorp.com",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.10, 0.18, 0.30, 0.45, 0.58], "absent": [],
        "price": (2.4, 0.14, 0.30),
        # raters STUCK LOW and FLAT while verified evidence climbs -> the gap the market hasn't priced
        "msci": ["B", "B", "B", "B", "B"],
        "sust": [44, 44, 44, 44, 44], "sp": None,
        "story": "HERO Hidden Winner: verified renewables transition rising, raters lagging.",
    },
    {
        "id": "TNB", "ticker": "5347.KL", "name": "Tenaga Nasional", "country": "Malaysia",
        "exchange": "KLSE", "domain": "tnb.com.my",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.38, 0.42, 0.48, 0.52, 0.56], "absent": [],
        "price": (13.5, 0.01, 0.20),
        "msci": ["A", "A", "AA", "AA", "AA"],
        "sust": [30, 29, 28, 27, 26], "sp": None,
        "story": "National incumbent: steady disclosure, raters already generous.",
    },
    {
        "id": "YTLP", "ticker": "6742.KL", "name": "YTL Power International", "country": "Malaysia",
        "exchange": "KLSE", "domain": "ytlpowerinternational.com",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.22, 0.28, 0.36, 0.46, 0.55], "absent": ["water_management"],
        "price": (0.78, 0.35, 0.38),
        "msci": ["BB", "BB", "BB", "BB", "BB"],
        "sust": [40, 39, 38, 37, 36], "sp": None,
        "story": "Improver: overseas generation plus data-centre build-out; raters stale.",
    },
    {
        "id": "EGCO", "ticker": "EGCO.BK", "name": "Electricity Generating", "country": "Thailand",
        "exchange": "SET", "domain": "egco.com",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.52, 0.48, 0.44, 0.40, 0.36], "absent": [],
        "price": (320.0, -0.14, 0.26),
        "msci": ["BBB", "BBB", "BB", "BB", "BB"],
        "sust": [34, 35, 36, 37, 38], "sp": None,
        "story": "Value Trap: evidence deteriorating as the thermal fleet ages.",
    },
    {
        "id": "RATCH", "ticker": "RATCH.BK", "name": "Ratch Group", "country": "Thailand",
        "exchange": "SET", "domain": "ratch.co.th",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.44, 0.45, 0.46, 0.46, 0.47], "absent": [],
        "price": (70.0, -0.12, 0.24),
        "msci": ["BB", "BB", "BB", "BB", "BB"],
        "sust": [36, 36, 35, 35, 34], "sp": None,
        "story": "Mid-pack and flat: disclosure plateaued, raters unmoved.",
    },
    {
        "id": "BGRIM", "ticker": "BGRIM.BK", "name": "B.Grimm Power", "country": "Thailand",
        "exchange": "SET", "domain": "bgrimmpower.com",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.30, 0.38, 0.47, 0.56, 0.64], "absent": [],
        "price": (45.0, -0.14, 0.32),
        "msci": ["BBB", "BBB", "BBB", "BBB", "BBB"],
        "sust": [32, 30, 29, 28, 27], "sp": None,
        "story": "Hidden Winner: fastest renewables shift in the panel, price de-rated.",
    },
    {
        "id": "GULF", "ticker": "GULF.BK", "name": "Gulf Development", "country": "Thailand",
        "exchange": "SET", "domain": "gulf.co.th",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.40, 0.48, 0.56, 0.64, 0.72], "absent": [],
        "price": (52.0, 0.05, 0.28),
        "msci": ["BBB", "BBB", "A", "A", "A"],
        "sust": [28, 26, 25, 24, 23], "sp": None,
        "story": "Future Leader: high disclosure and still climbing.",
    },
    {
        "id": "PGAS", "ticker": "PGAS.JK", "name": "Perusahaan Gas Negara", "country": "Indonesia",
        "exchange": "IDX", "domain": "pgn.co.id",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.62, 0.60, 0.56, 0.52, 0.48], "absent": ["ghg_emissions"],
        "price": (2200.0, -0.08, 0.30),
        # raters still HIGH while evidence quietly deteriorates -> overrated
        "msci": ["A", "A", "A", "A", "A"],
        "sust": [26, 27, 28, 29, 30], "sp": None,
        "story": "Overrated Leader: gas transition story, evidence sliding, raters generous.",
    },
    {
        "id": "POWR", "ticker": "POWR.JK", "name": "Cikarang Listrindo", "country": "Indonesia",
        "exchange": "IDX", "domain": "listrindo.com",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.18, 0.20, 0.24, 0.28, 0.32], "absent": ["water_management", "air_quality"],
        "price": (500.0, 0.11, 0.26),
        "msci": ["BB", "BB", "BB", "BB", "BB"],
        "sust": [46, 45, 45, 44, 44], "sp": None,
        "story": "Thin discloser: small industrial-estate utility, little verifiable evidence.",
    },
    {
        "id": "POW", "ticker": "POW.VN", "name": "PetroVietnam Power", "country": "Vietnam",
        "exchange": "HOSE", "domain": "pvpower.vn",
        "sector": "Utilities", "industry": "Electric Utilities & Power Generators",
        "vf": [0.12, 0.14, 0.18, 0.22, 0.26], "absent": ["water_management", "air_quality"],
        "price": (14000.0, 0.0, 0.30),
        # No MSCI coverage exists for PV Power; the seed keeps a placeholder but the real
        # channel stays N.A. because MarketScreener publishes no ESG MSCI letter for it.
        "msci": ["BB", "BB", "BB", "BB", "BB"],
        "sust": [50, 50, 49, 49, 48], "sp": None,
        "story": "Lowest disclosure in the panel; no MSCI coverage at all.",
    },
]

# There is no reference panel. An invented peer group made every percentile and every
# industry median a rank against companies that do not exist; the panel is these ten real
# ASEAN utilities and nothing else. All ten share one sector and one SASB rubric, so
# percentiles rank utility-against-utility and config.MIN_PEERS_FOR_SECTOR_RANK is met by
# the sector cohort itself rather than falling back to the whole panel.
#
# S&P Global is absent by decision, not by oversight: no public S&P ESG score could be
# obtained for these names, so "sp" is None throughout and sp_global is written NULL. The
# contributing rater channels are MSCI (real, from MarketScreener) and Sustainalytics.


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
    msci, sust, sp, vf_series = demo_series(c)
    for i, year in enumerate(config.YEARS):
        conn.execute(
            "INSERT OR REPLACE INTO rater_scores VALUES (?,?,?,?,?)",
            (cid, year, msci[i], float(sust[i]),
             None if sp[i] is None else float(sp[i])),
        )
    start, drift, vol = c["price"]
    for row in gen_prices(rng, start, drift, vol):
        conn.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                     (cid, row["week_date"], row["open"], row["high"], row["low"], row["close"], row["volume"]))
    conn.execute("INSERT OR REPLACE INTO fundamentals VALUES (?,?,?,?)",
                 (cid, "2023", round(rng.uniform(8, 22), 1), round(rng.uniform(2, 5), 2)))

    # documents + evidence per year, with verified fraction controlling the trajectory
    for i, year in enumerate(config.YEARS):
        vf = vf_series[i]
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
        if vf_series[-1] - vf_series[0] > 0.2 and year in (2021, 2022):
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
        # one emissions_verified event per company-year, even if several climate
        # topics are verified that year (otherwise the witness shows duplicate pins)
        exists = conn.execute(
            "SELECT 1 FROM events WHERE company_id=? AND date=? AND type='emissions_verified'",
            (cid, f"{year}-12-31")).fetchone()
        if not exists:
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                         (cid, f"{year}-12-31", "emissions_verified",
                          f"Emissions verified by {authority} ({year})", None))


def _insert_compliance(conn, c, regs):
    cid = c["id"]
    _, _, _, vf_series = demo_series(c)
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
                vf = vf_series[config.YEARS.index(year)]
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


def _summary(conn):
    for t in ("universe", "rater_scores", "prices", "documents", "evidence", "events", "reg_compliance"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {n:6d} rows")


if __name__ == "__main__":
    print("Building seed esg.db ...")
    build()
    print(f"Done -> {config.DB_PATH}")
