import { useEffect, useState } from "react";
import type { CompanyDetail, CompanyRow, MatrixPoint, NewsData } from "../types";

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
};

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
