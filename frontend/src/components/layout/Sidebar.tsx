import {
  LayoutDashboard,
  Sparkles,
  Leaf,
  Compass,
  BookMarked,
  Settings,
  Activity,
  Newspaper,
} from "lucide-react";
import {
  useNavigation,
  type RouteName,
} from "../../navigation/NavigationContext";

type NavItem = {
  key: Exclude<RouteName, "company" | "evidenceCompany">;
  label: string;
  icon: React.ReactNode;
};

const PRIMARY: NavItem[] = [
  { key: "dashboard", label: "Dashboard", icon: <LayoutDashboard size={17} /> },
  { key: "assistant", label: "AI Agent", icon: <Sparkles size={17} /> },
];

const ENGINE: NavItem[] = [
  { key: "evidence", label: "Evidence Engine", icon: <Activity size={17} /> },
  { key: "news", label: "Live News", icon: <Newspaper size={17} /> },
];

const BROWSE: NavItem[] = [
  { key: "explore", label: "Explore", icon: <Compass size={17} /> },
  { key: "watchlists", label: "Watchlists", icon: <BookMarked size={17} /> },
  { key: "settings", label: "Settings", icon: <Settings size={17} /> },
];

export default function Sidebar() {
  const { route, navigate } = useNavigation();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-hairline bg-surface px-3 py-5 md:flex">
      <div className="flex items-center gap-2.5 px-2 pb-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-pos/15 text-pos">
          <Leaf size={18} />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-txt">ESG Intelligence</p>
          <p className="text-[11px] text-faint">Sustainability analytics</p>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Workspace
        </p>
        {PRIMARY.map((item) => (
          <NavButton
            key={item.key}
            item={item}
            active={route.name === item.key}
            onClick={() => navigate({ name: item.key })}
          />
        ))}
      </nav>

      <nav className="mt-6 flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Evidence engine
        </p>
        {ENGINE.map((item) => (
          <NavButton
            key={item.key}
            item={item}
            active={route.name === item.key}
            onClick={() => navigate({ name: item.key })}
          />
        ))}
      </nav>

      <nav className="mt-6 flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Browse
        </p>
        {BROWSE.map((item) => (
          <NavButton
            key={item.key}
            item={item}
            active={route.name === item.key}
            onClick={() => navigate({ name: item.key })}
          />
        ))}
      </nav>

      <div className="mt-auto rounded-lg border border-hairline bg-canvas/40 p-3">
        <p className="text-xs font-medium text-txt">Q2 2026 universe</p>
        <p className="mt-0.5 text-[11px] leading-snug text-faint">
          95 global companies screened across 10 sectors and 6 regions.
        </p>
      </div>
    </aside>
  );
}

function NavButton({
  item,
  active,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition ${
        active
          ? "bg-raised text-txt"
          : "text-muted hover:bg-raised/60 hover:text-txt"
      }`}
    >
      <span className={active ? "text-pos" : "text-faint"}>{item.icon}</span>
      {item.label}
    </button>
  );
}
