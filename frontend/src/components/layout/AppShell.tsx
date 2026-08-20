import {
  BookMarked,
  Compass,
  LayoutDashboard,
  Leaf,
  Newspaper,
  Settings,
  Sparkles,
} from "lucide-react";
import Sidebar from "./Sidebar";
import { useNavigation } from "../../navigation/NavigationContext";
import type { RouteName } from "../../navigation/NavigationContext";

type MobileNavItem = {
  key: Exclude<RouteName, "company" | "evidenceCompany">;
  label: string;
  icon: React.ReactNode;
};

const MOBILE_NAV: MobileNavItem[] = [
  { key: "dashboard", label: "Dashboard", icon: <LayoutDashboard size={16} /> },
  { key: "assistant", label: "AI Agent", icon: <Sparkles size={16} /> },
  { key: "news", label: "Live News", icon: <Newspaper size={16} /> },
  { key: "explore", label: "Explore", icon: <Compass size={16} /> },
  { key: "watchlists", label: "Watchlists", icon: <BookMarked size={16} /> },
  { key: "settings", label: "Settings", icon: <Settings size={16} /> },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { route, navigate } = useNavigation();
  const routeKey =
    route.name === "company"
      ? `company-${route.id}`
      : route.name === "evidenceCompany"
        ? `evidenceCompany-${route.id}`
        : route.name;
  return (
    <div className="flex h-[100dvh] overflow-hidden bg-canvas text-txt">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="safe-top flex shrink-0 items-center justify-between border-b border-hairline bg-surface/95 px-3 py-2.5 backdrop-blur md:hidden">
          <div className="flex items-center gap-2">
            <Leaf size={16} className="text-pos" />
            <span className="text-sm font-semibold">ESG Intelligence</span>
          </div>
          <div className="-mr-1 flex max-w-[58vw] gap-0.5 overflow-x-auto">
            {MOBILE_NAV.map((item) => (
              <button
                key={item.key}
                onClick={() => navigate({ name: item.key })}
                className={`flex shrink-0 items-center justify-center rounded-md px-2.5 ${
                  route.name === item.key ? "bg-raised text-txt" : "text-muted"
                }`}
                aria-label={item.label}
              >
                {item.icon}
              </button>
            ))}
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain">
          <div key={routeKey} className="h-full animate-fade-up">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
