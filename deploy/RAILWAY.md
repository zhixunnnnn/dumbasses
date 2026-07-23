# Railway Deployment

This repository deploys to Railway as a single Nixpacks service:

- Nixpacks installs Python backend dependencies from `backend/requirements.txt`.
- Nixpacks installs frontend dependencies with `npm ci --prefix frontend`.
- Nixpacks builds the Vite app with `npm run build --prefix frontend`.
- Railway starts `backend.app.railway:app`, which serves both `/api/*` and the compiled frontend from `frontend/dist`.

## Required Railway Variables

Set these in the Railway service variables:

```text
OPENROUTER_API_KEY=...
BRIGHTDATA_API_KEY=...
```

Optional:

```text
BRIGHTDATA_API_KEY_FALLBACK=...
AGENT_DAILY_LIMIT=100
```

The app listens on Railway's injected `PORT`. Do not hardcode a port in Railway.

## Health Check

Railway uses:

```text
/api/health
```

Expected response:

```json
{"status":"ok","service":"polyfintech-esg"}
```
