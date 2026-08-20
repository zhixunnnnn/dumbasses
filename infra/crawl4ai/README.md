# Crawl4AI — page rendering and extraction

Headless-browser fetcher for the Crawl4AI + SearXNG provider. SearXNG finds URLs;
this service turns each one into readable text.

## Railway

`railway.json` in this directory carries the builder, healthcheck, and restart
policy — but only if the service's **Config-as-code path** is set to
`railway.json`. Without that, Railway silently falls back to Railpack defaults
and ignores this file.

Everything below it *cannot* express, and must be set on the service itself:

| Setting | Value | Why |
| --- | --- | --- |
| Root directory | `/infra/crawl4ai` | Otherwise Railway builds the repo root — the whole app — instead of this image |
| Config-as-code path | `railway.json` | Without it the file below is ignored |
| Domain target port | `11235` | Crawl4AI does not read `$PORT` |
| `PORT` | `11235` | Railway probes the port it injects; the app hardcodes 11235, so they must agree or the healthcheck never passes |
| Watch patterns | `infra/crawl4ai/**` | Avoids rebuilding on unrelated commits |

Missing `PORT` or the root directory reproduces the two failed deploys in this
project's history: a build of the wrong thing, then a healthcheck that times out
against a port nothing is listening on.

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
