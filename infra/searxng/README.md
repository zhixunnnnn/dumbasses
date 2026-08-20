# SearXNG — discovery for the Crawl4AI + SearXNG provider

Private metasearch instance. The backend only ever uses the JSON API
(`GET /search?format=json`); the HTML UI exists solely for debugging.

## Railway

| Setting | Value |
| --- | --- |
| Root directory | `/infra/searxng` |
| Builder | Dockerfile (`infra/searxng/railway.json`) |
| Target port | `8080` |

## The two settings that actually matter

`settings.yml` carries the configuration that makes the JSON API usable, and both
lines are load-bearing:

- **`limiter: false`** — the limiter is SearXNG's bot filter. With it on, the JSON
  API answers `403` for every request, which the provider used to surface as an
  empty result set, so the whole discovery path looked like "no results found"
  rather than a misconfiguration. The instance is private and never exposed
  onward, so the filter has nothing to protect.
- **`json` in `search.formats`** — without it, `format=json` is refused outright.

`secret_key` is the literal `ultrasecretkey`; the container entrypoint rewrites it
with a random value on boot.

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
