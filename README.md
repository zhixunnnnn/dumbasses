# PolyFintech 2026

React + FastAPI starter for a fintech operations dashboard.

## Structure

- `frontend/` - Vite, React, TypeScript, Tailwind CSS
- `backend/` - FastAPI app with typed API responses

## Run Locally

Install frontend dependencies:

```bash
cd frontend
npm install
npm run dev
```

Install backend dependencies and run from the **repo root** (the engine uses
absolute `backend.*` imports):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

On first start the ESG Evidence Engine seeds its database and precomputes the
dashboard JSON offline (no network required); subsequent starts reuse it.

Open the frontend at `http://localhost:5173`.

The frontend proxies `/api/*` requests to `http://localhost:8000`.

## Features

- **AI Assistant** — chat sessions, streaming research agent, source-backed PDF reports (`/api/assistant/*`).
- **ESG Evidence Engine** — scoring/signal/witness/forecast over a seeded Singapore universe, served as `/api/companies`, `/api/matrix`, `/api/signals`, `/api/company/{id}`, and live `/api/news`. UI lives under the "Evidence Engine" and "Live News" sidebar sections.

