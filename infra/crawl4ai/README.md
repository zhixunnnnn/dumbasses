# Crawl4AI — page rendering and extraction

Headless-browser fetcher for the Crawl4AI + SearXNG provider. SearXNG finds URLs;
this service turns each one into readable text.

## Railway

| Setting | Value |
| --- | --- |
| Root directory | `/infra/crawl4ai` |
| Builder | Dockerfile (`infra/crawl4ai/railway.json`) |
| Target port | `11235` |
| Healthcheck | `/schema` |

Pinned to `unclecode/crawl4ai:0.8.0`. Auth is off in the image's default config
(`security.jwt_enabled: false`), so no token is needed; keep the service on the
private network rather than adding one.

Railway cannot raise a container's `/dev/shm`, which normally makes Chromium
unstable — but Crawl4AI's default browser arguments already include
`--disable-dev-shm-usage`, so the small default shm is not a problem here.

## Why the Dockerfile patches supervisord

The upstream image starts gunicorn with `--bind 0.0.0.0:11235`, an IPv4-only
listener. Railway's internal network is IPv6, and both the healthcheck and the
private-network hostname go through it, so every request returned 502 while the
container logged a clean startup and sat at 0.7 GB of its 8 GB limit — the
service looked healthy from the inside and was simply unreachable.

The Dockerfile rewrites the bind to `[::]:11235`. That is a dual-stack socket
(`net.ipv6.bindv6only` defaults to 0), so plain IPv4 clients such as
docker-compose still work. SearXNG needs no such patch — its server already
listens on `:::8080`.

## Endpoints the adapter uses

`fetch_crawl4ai` tries them in this order:

1. **`POST /md`** — flat body (`{"url": ..., "f": "fit"}`), returns
   `{"markdown": ...}`. Preferred because the request shape has been stable
   across releases.
2. **`POST /crawl`** — fallback for builds without `/md`. Its `browser_config` and
   `crawler_config` are sent in the explicit `{"type": ..., "params": {...}}`
   serialization, which the server deserializes on every version; bare kwargs are
   only accepted on newer ones.

If both come back empty, the adapter raises with both underlying errors rather
than reporting the page as simply unfetchable.

## Pointing the backend at it

Set `CRAWL4AI_BASE_URL`, or paste the URL into Settings → Scraping providers →
Self-hosted endpoints. The value is normalized, so an origin, a trailing slash,
or a pasted `/crawl` URL all resolve the same. Settings → **Test connection**
probes it.

Prefer `http://crawl4ai.railway.internal:11235` to keep it off the public
internet.

## Checking it by hand

```bash
curl -s "$CRAWL4AI_BASE_URL/schema" | head -c 200
```

0.8.0 has **no `/health` route** — `/` only redirects to the playground, so a
healthcheck pointed at `/health` leaves the deploy stuck in DEPLOYING until it
times out. `/schema` is a plain JSON GET present on every release.
