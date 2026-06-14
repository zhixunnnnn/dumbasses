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
import { COMPANY_BY_ID } from "../../data/companies";

const STORAGE_KEY = "polyfintech.watchlist.v1";

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

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (id): id is string => typeof id === "string" && id in COMPANY_BY_ID,
    );
  } catch {
    return [];
  }
}

export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [watchlistIds, setWatchlistIds] = useState<string[]>(readStoredIds);

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

  const watchlistCompanies = useMemo(
    () =>
      watchlistIds
        .map((id) => COMPANY_BY_ID[id])
        .filter((company): company is Company => Boolean(company)),
    [watchlistIds],
  );

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
