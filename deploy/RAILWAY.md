# Railway Deployment

This repository deploys to Railway as a single Dockerfile service:

- The Node build stage installs and compiles the Vite frontend.
- The Python runtime stage installs `backend/requirements.txt`.
- Railway starts `backend.app.railway:app`, which serves both `/api/*` and the compiled frontend from `frontend/dist`.

## Required Railway Variables

Set these in the Railway service variables:

```text
OPENROUTER_API_KEY=...
BRIGHTDATA_API_KEY=...
BRIGHTDATA_ZONE=web_unlocker1
BRIGHTDATA_SERP_ZONE=serp_api1
```

Optional:

```text
BRIGHTDATA_API_KEY_FALLBACK=...
OPENROUTER_MODEL=deepseek/deepseek-v4-flash
AGENT_DAILY_LIMIT=100
```

The app listens on Railway's injected `PORT`. Do not hardcode a port in Railway.

## Persistent SQLite Data

Attach a Railway volume to the service so chat history and the ESG database
survive deployments. The app automatically uses Railway's
`RAILWAY_VOLUME_MOUNT_PATH`; `/data` is the recommended mount path.

Because Railway volumes are mounted as root while this image runs as a non-root
user, add this Railway service variable when attaching the volume:

```text
RAILWAY_RUN_UID=0
```

On the first start, the committed databases are copied into an empty volume.
Later writes stay on the volume and are not overwritten by new deployments.

## Health Check

Railway uses:

```text
/api/health
```

Expected response:

```json
{"status":"ok","service":"polyfintech-esg"}
```
