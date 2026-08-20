# SearXNG — discovery for the Crawl4AI + SearXNG provider

Private metasearch instance. The backend only ever uses the JSON API
(`GET /search?format=json`); the HTML UI exists solely for debugging.

## Railway

`railway.json` in this directory carries the builder and restart policy — but
only if the service's **Config-as-code path** is set to `railway.json`. Without
that, Railway silently falls back to Railpack defaults and ignores the file.

Settings it cannot express, which must be set on the service itself:

| Setting | Value | Why |
| --- | --- | --- |
| Root directory | `/infra/searxng` | Otherwise Railway builds the repo root — the whole app — instead of this image |
| Config-as-code path | `railway.json` | Without it the file below is ignored |
| Domain target port | `8080` | SearXNG's own default |
| `SEARXNG_SECRET` | a random 32-byte hex string | Required — see below; without it the container will not start |
| Watch patterns | `infra/searxng/**` | Avoids rebuilding on unrelated commits |

## The two settings that actually matter

`settings.yml` carries the configuration that makes the JSON API usable, and both
lines are load-bearing:

- **`limiter: false`** — the limiter is SearXNG's bot filter. With it on, the JSON
  API answers `403` for every request, which the provider used to surface as an
  empty result set, so the whole discovery path looked like "no results found"
  rather than a misconfiguration. The instance is private and never exposed
  onward, so the filter has nothing to protect.
- **`json` in `search.formats`** — without it, `format=json` is refused outright.

**`SEARXNG_SECRET` must be set on the service.** The image entrypoint rewrites the
`ultrasecretkey` placeholder only in a settings file it generates itself, not in
one copied to `/etc/searxng/settings.yml`, and SearXNG refuses to start while the
placeholder is in place:

```
ERROR:searx.webapp: server.secret_key is not changed.
```

The environment variable overrides the file, so setting it is the fix.

## Pointing the backend at it

Set `SEARXNG_BASE_URL`, or paste the URL into Settings → Scraping providers →
Self-hosted endpoints. Either way the value is normalized (scheme added, trailing
slash and any endpoint path stripped), so the origin and the full `/search` URL
both work. Settings → **Test connection** probes the live endpoint and reports
the result count or the exact HTTP error.

Prefer the private network URL (`http://searxng.railway.internal:8080`) so the
instance is not reachable from the public internet.

## Checking it by hand

```bash
curl -s "$SEARXNG_BASE_URL/search?q=esg&format=json" | head -c 400
```

A `403` means the limiter is back on. An HTML body means `json` is missing from
`search.formats`.
