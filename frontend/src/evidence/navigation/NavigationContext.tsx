// Navigation adapter for the embedded ESG Evidence Engine.
//
// jw's evidence pages import `useNavigation` from "../../navigation/NavigationContext".
// Inside this `evidence/` subtree that path resolves here, so we re-expose the same
// shape jw expects while delegating to the app's real router. Company drill-ins use
// the dedicated "evidenceCompany" route and "back" returns to the evidence dashboard,
// keeping the evidence section fully separate from main's own company pages.
import { useNavigation as useAppNavigation } from "../../navigation/NavigationContext";

export function useNavigation() {
  const nav = useAppNavigation();
  return {
    route: nav.route,
    navigate: nav.navigate,
    openCompany: (id: string) => nav.navigate({ name: "evidenceCompany", id }),
    goBack: () => nav.navigate({ name: "evidence" }),
  };
}
