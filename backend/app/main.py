from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    value: int
    change: str


class Portfolio(BaseModel):
    customer_count: int
    transaction_volume: int
    risk_score: int
    uptime: str
    products: list[Product]


app = FastAPI(title="PolyFintech 2026 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "polyfintech2026"}


@app.get("/api/portfolio", response_model=Portfolio)
def portfolio() -> Portfolio:
    return Portfolio(
        customer_count=12840,
        transaction_volume=4280000,
        risk_score=18,
        uptime="99.98%",
        products=[
            Product(name="Digital Wallets", value=1820000, change="+18.4%"),
            Product(name="SME Lending", value=1410000, change="+11.2%"),
            Product(name="Cross-border Pay", value=1050000, change="+9.7%"),
        ],
    )

