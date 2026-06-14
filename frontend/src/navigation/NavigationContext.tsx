import { createContext, useCallback, useContext, useMemo, useState } from "react";

export type Route = { name: "dashboard" } | { name: "company"; id: string } | { name: "news" };
export type RouteName = Route["name"];

type NavigationValue = {
  route: Route;
  navigate: (route: Route) => void;
  openCompany: (id: string) => void;
  goBack: () => void;
};

const NavigationContext = createContext<NavigationValue | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [route, setRoute] = useState<Route>({ name: "dashboard" });

  const navigate = useCallback((next: Route) => setRoute(next), []);
  const openCompany = useCallback((id: string) => setRoute({ name: "company", id }), []);
  const goBack = useCallback(() => setRoute({ name: "dashboard" }), []);

  const value = useMemo(
    () => ({ route, navigate, openCompany, goBack }),
    [route, navigate, openCompany, goBack],
  );
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigation(): NavigationValue {
  const ctx = useContext(NavigationContext);
  if (!ctx) throw new Error("useNavigation must be used within NavigationProvider");
  return ctx;
}
