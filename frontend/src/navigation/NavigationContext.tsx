import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export type Route =
  | { name: "dashboard" }
  | { name: "assistant" }
  | { name: "explore" }
  | { name: "watchlists" }
  | { name: "interpretability" }
  | { name: "governance" }
  | { name: "settings" }
  | { name: "news" }
  | { name: "evidenceCompany"; id: string };

export type RouteName = Route["name"];

type NavigationValue = {
  route: Route;
  navigate: (route: Route) => void;
  openCompany: (id: string) => void;
  goBack: () => void;
};

const NavigationContext = createContext<NavigationValue | null>(null);

const DEFAULT_ROUTE: Route = { name: "dashboard" };

// Every page owns a URL so reloads, bookmarks and browser back/forward work.
// The dashboard lives at "/" and company drill-ins carry their id in the path.
function routeToPath(route: Route): string {
  switch (route.name) {
    case "dashboard":
      return "/";
    case "evidenceCompany":
      return `/evidence/company/${encodeURIComponent(route.id)}`;
    default:
      return `/${route.name}`;
  }
}

const SIMPLE_ROUTES: RouteName[] = [
  "assistant",
  "explore",
  "watchlists",
  "interpretability",
  "governance",
  "settings",
  "news",
];

function pathToRoute(pathname: string): Route {
  const segments = pathname.split("/").filter(Boolean).map(decodeURIComponent);

  if (segments.length === 0) return DEFAULT_ROUTE;

  if (segments.length === 1) {
    const name = SIMPLE_ROUTES.find((candidate) => candidate === segments[0]);
    return name ? ({ name } as Route) : DEFAULT_ROUTE;
  }

  if (
    segments.length === 3 &&
    segments[0] === "evidence" &&
    segments[1] === "company"
  ) {
    return { name: "evidenceCompany", id: segments[2] };
  }

  return DEFAULT_ROUTE;
}

export function NavigationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [route, setRoute] = useState<Route>(() =>
    pathToRoute(window.location.pathname),
  );
  const [previous, setPrevious] = useState<Route>(DEFAULT_ROUTE);
  const mounted = useRef(false);

  // Keep the address bar in sync. A path that already matches means the change
  // came from the browser (back/forward), so there is nothing to push.
  useEffect(() => {
    const path = routeToPath(route);
    if (path === window.location.pathname) return;
    if (mounted.current) {
      window.history.pushState(null, "", path);
    } else {
      // Normalise an unknown entry URL without leaving a dead history entry.
      window.history.replaceState(null, "", path);
    }
  }, [route]);

  useEffect(() => {
    mounted.current = true;
    const onPopState = () => setRoute(pathToRoute(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: Route) => {
    setRoute((current) => {
      setPrevious(current);
      return next;
    });
  }, []);

  // Company drill-ins go to the evidence profile, keyed by the engine id.
  const openCompany = useCallback(
    (id: string) => navigate({ name: "evidenceCompany", id }),
    [navigate],
  );

  const goBack = useCallback(() => {
    setRoute(previous.name === "evidenceCompany" ? DEFAULT_ROUTE : previous);
  }, [previous]);

  const value = useMemo(
    () => ({ route, navigate, openCompany, goBack }),
    [route, navigate, openCompany, goBack],
  );

  return (
    <NavigationContext.Provider value={value}>
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation(): NavigationValue {
  const ctx = useContext(NavigationContext);
  if (!ctx) {
    throw new Error("useNavigation must be used within NavigationProvider");
  }
  return ctx;
}
