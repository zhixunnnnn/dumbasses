import { useEffect, useState } from "react";
import type { BriefingData, CompanyDetail, CompanyRow, MatrixPoint, NewsData, RegulationInfo, SatelliteData } from "../types";

const BASE = "/api";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  companies: () => getJSON<CompanyRow[]>("/companies"),
  matrix: () => getJSON<MatrixPoint[]>("/matrix"),
  signals: () => getJSON<CompanyRow[]>("/signals"),
  company: (id: string) => getJSON<CompanyDetail>(`/company/${id}`),
  news: () => getJSON<NewsData>("/news"),
  regulations: () => getJSON<RegulationInfo[]>("/regulations"),
  briefing: () => getJSON<BriefingData>("/dashboard/briefing"),
  satellite: (id: string) => getJSON<SatelliteData>(`/satellite/${id}`),
};

const CACHE_PREFIX = "esg-cache:";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;   // the briefing regenerates once per SG day

type CacheEntry<T> = { at: number; data: T };

function cacheKey(key: string) {
  return `${CACHE_PREFIX}${key}`;
}

/** Cached payload for `key`, or null when absent, unreadable, or past the TTL. */
function readCache<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(cacheKey(key));
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry<T>;
    if (!entry || typeof entry.at !== "number") return null;
    if (Date.now() - entry.at > CACHE_TTL_MS) {
      window.localStorage.removeItem(cacheKey(key));
      return null;
    }
    return entry.data;
  } catch {
    return null;   // private mode, disabled storage, or a corrupt entry
  }
}

/** Drop the oldest cached payloads so a fresh one fits. Company details run ~150KB
 *  each, so a full roster can crowd a 5MB origin quota. */
function evictOldest(exceptKey: string) {
  try {
    const entries: Array<{ key: string; at: number }> = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (!key || !key.startsWith(CACHE_PREFIX) || key === exceptKey) continue;
      try {
        entries.push({ key, at: JSON.parse(window.localStorage.getItem(key) ?? "{}").at ?? 0 });
      } catch {
        entries.push({ key, at: 0 });
      }
    }
    entries.sort((a, b) => a.at - b.at);
    for (const entry of entries.slice(0, Math.max(1, Math.ceil(entries.length / 2)))) {
      window.localStorage.removeItem(entry.key);
    }
  } catch {
    /* nothing we can do; the write below just fails again and is skipped */
  }
}

function writeCache<T>(key: string, data: T) {
  const payload = JSON.stringify({ at: Date.now(), data } satisfies CacheEntry<T>);
  try {
    window.localStorage.setItem(cacheKey(key), payload);
  } catch {
    evictOldest(cacheKey(key));
    try {
      window.localStorage.setItem(cacheKey(key), payload);
    } catch {
      /* over quota even after eviction — run uncached rather than fail the render */
    }
  }
}

type AsyncState<T> = { data: T | null; loading: boolean; error: string | null };

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });
  useEffect(() => {
    let alive = true;
    setState({ data: null, loading: true, error: null });
    fetcher()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e) => alive && setState({ data: null, loading: false, error: String(e) }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** Like `useApi`, but renders the last cached payload immediately and refreshes it in
 *  the background. A revisit or a reload paints from cache with no spinner; the network
 *  result replaces it when it lands. Cache misses behave exactly like `useApi`. */
export function useCachedApi<T>(
  key: string,
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> & { cached: boolean } {
  const [state, setState] = useState<AsyncState<T> & { cached: boolean }>(() => {
    const cached = readCache<T>(key);
    return { data: cached, loading: cached === null, error: null, cached: cached !== null };
  });

  useEffect(() => {
    let alive = true;
    const cached = readCache<T>(key);
    setState({ data: cached, loading: cached === null, error: null, cached: cached !== null });
    fetcher()
      .then((data) => {
        if (!alive) return;
        writeCache(key, data);
        setState({ data, loading: false, error: null, cached: false });
      })
      .catch((e) => {
        if (!alive) return;
        // Keep showing cached data when the refresh fails; only a cold miss is an error.
        setState((prev) =>
          prev.data !== null
            ? { ...prev, loading: false }
            : { data: null, loading: false, error: String(e), cached: false },
        );
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
