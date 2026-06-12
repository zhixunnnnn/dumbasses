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

Install backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open the frontend at `http://localhost:5173`.

The frontend proxies `/api/*` requests to `http://localhost:8000`.

