import { LayoutDashboard, Sparkles, Leaf } from "lucide-react";
import Sidebar from "./Sidebar";
import { useNavigation } from "../../navigation/NavigationContext";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { route, navigate } = useNavigation();
  const routeKey =
    route.name === "company" ? `company-${route.id}` : route.name;
  return (
    <div className="flex h-screen overflow-hidden bg-canvas text-txt">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-hairline px-4 py-2.5 md:hidden">
          <div className="flex items-center gap-2">
            <Leaf size={16} className="text-pos" />
            <span className="text-sm font-semibold">ESG Intelligence</span>
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => navigate({ name: "dashboard" })}
              className={`rounded-md p-1.5 ${
                route.name === "dashboard" ? "bg-raised text-txt" : "text-muted"
              }`}
              aria-label="Dashboard"
            >
              <LayoutDashboard size={16} />
            </button>
            <button
              onClick={() => navigate({ name: "assistant" })}
              className={`rounded-md p-1.5 ${
                route.name === "assistant" ? "bg-raised text-txt" : "text-muted"
              }`}
              aria-label="AI Assistant"
            >
              <Sparkles size={16} />
            </button>
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
