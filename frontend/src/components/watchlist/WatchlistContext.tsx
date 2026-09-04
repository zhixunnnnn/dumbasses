import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Company } from "../../types";
import { COMPANY_BY_ID, useCompanies } from "../../data/companies";

const STORAGE_KEY = "polyfintech.watchlist.v2";
const LEGACY_STORAGE_KEY = "polyfintech.watchlist.v1";
const DEFAULT_WATCHLIST_IDS = ["U96", "TNB", "GULF", "PGAS"];

type WatchlistValue = {
  watchlistIds: string[];
  watchlistCompanies: Company[];
  addToWatchlist: (id: string) => void;
  removeFromWatchlist: (id: string) => void;
  toggleWatchlist: (id: string) => void;
  isWatchlisted: (id: string) => boolean;
  clearWatchlist: () => void;
};

const WatchlistContext = createContext<WatchlistValue | null>(null);

function readStoredIds(): string[] {
  if (typeof window === "undefined") return [];

  const stored = parseStoredIds(window.localStorage.getItem(STORAGE_KEY));
  if (stored !== null) return stored;

  const legacy = parseStoredIds(
    window.localStorage.getItem(LEGACY_STORAGE_KEY),
  );
  if (legacy?.length) return legacy;

  return DEFAULT_WATCHLIST_IDS;
}

function parseStoredIds(raw: string | null): string[] | null {
  if (raw === null) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.filter(
      (id): id is string => typeof id === "string" && id in COMPANY_BY_ID,
    );
  } catch {
    return null;
  }
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [watchlistIds, setWatchlistIds] = useState<string[]>(readStoredIds);
  const { companies } = useCompanies();

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlistIds));
  }, [watchlistIds]);

  const addToWatchlist = useCallback((id: string) => {
    if (!(id in COMPANY_BY_ID)) return;
    setWatchlistIds((current) =>
      current.includes(id) ? current : [...current, id],
    );
  }, []);

  const removeFromWatchlist = useCallback((id: string) => {
    setWatchlistIds((current) => current.filter((item) => item !== id));
  }, []);

  const toggleWatchlist = useCallback(
    (id: string) => {
      setWatchlistIds((current) => {
        if (current.includes(id)) {
          return current.filter((item) => item !== id);
        }
        return id in COMPANY_BY_ID ? [...current, id] : current;
      });
    },
    [],
  );

  const clearWatchlist = useCallback(() => {
    setWatchlistIds([]);
  }, []);

  const watchlistCompanies = useMemo(() => {
    const byId = new Map(companies.map((company) => [company.id, company]));
    return watchlistIds
      .map((id) => byId.get(id))
      .filter((company): company is Company => Boolean(company));
  }, [companies, watchlistIds]);

  const watchlistSet = useMemo(() => new Set(watchlistIds), [watchlistIds]);

  const isWatchlisted = useCallback(
    (id: string) => watchlistSet.has(id),
    [watchlistSet],
  );

  const value = useMemo(
    () => ({
      watchlistIds,
      watchlistCompanies,
      addToWatchlist,
      removeFromWatchlist,
      toggleWatchlist,
      isWatchlisted,
      clearWatchlist,
    }),
    [
      watchlistIds,
      watchlistCompanies,
      addToWatchlist,
      removeFromWatchlist,
      toggleWatchlist,
      isWatchlisted,
      clearWatchlist,
    ],
  );

  return (
    <WatchlistContext.Provider value={value}>
      {children}
    </WatchlistContext.Provider>
  );
}

export function useWatchlist(): WatchlistValue {
  const ctx = useContext(WatchlistContext);
  if (!ctx) {
    throw new Error("useWatchlist must be used within WatchlistProvider");
  }
  return ctx;
}
