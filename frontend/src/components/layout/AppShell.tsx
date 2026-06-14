import {
  Activity,
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
  { key: "assistant", label: "AI Assistant", icon: <Sparkles size={16} /> },
  { key: "evidence", label: "Evidence Engine", icon: <Activity size={16} /> },
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
    <div className="flex h-screen overflow-hidden bg-canvas text-txt">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-hairline px-4 py-2.5 md:hidden">
          <div className="flex items-center gap-2">
            <Leaf size={16} className="text-pos" />
            <span className="text-sm font-semibold">ESG Intelligence</span>
          </div>
          <div className="flex max-w-[52vw] gap-1 overflow-x-auto">
            {MOBILE_NAV.map((item) => (
              <button
                key={item.key}
                onClick={() => navigate({ name: item.key })}
                className={`shrink-0 rounded-md p-1.5 ${
                  route.name === item.key ? "bg-raised text-txt" : "text-muted"
                }`}
                aria-label={item.label}
              >
                {item.icon}
              </button>
            ))}
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div key={routeKey} className="h-full animate-fade-up">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
