import { LayoutDashboard, ShieldCheck, Microscope, Scale, FlaskConical } from "lucide-react";
import { useNavigation } from "../../navigation/NavigationContext";

export default function Sidebar() {
  const { route, navigate } = useNavigation();
  const isActive = route.name === "dashboard";

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-hairline bg-surface px-3 py-5 md:flex">
      <div className="flex items-center gap-2.5 px-2 pb-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-pos/15 text-pos">
          <ShieldCheck size={18} />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-txt">ESG Evidence Engine</p>
          <p className="text-[11px] text-faint">Evidence over opinion</p>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Workspace
        </p>
        <button
          onClick={() => navigate({ name: "dashboard" })}
          className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition ${
            isActive ? "bg-raised text-txt" : "text-muted hover:bg-raised/60 hover:text-txt"
          }`}
        >
          <span className={isActive ? "text-pos" : "text-faint"}>
            <LayoutDashboard size={17} />
          </span>
          Momentum Screener
        </button>
      </nav>

      <div className="mt-6 flex flex-col gap-2.5 px-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-faint">
          How it works
        </p>
        {[
          { icon: <Microscope size={15} />, t: "Verify claims", d: "Reports → evidence (3 states)" },
          { icon: <Scale size={15} />, t: "Measure divergence", d: "MSCI · Sustainalytics · S&P" },
          { icon: <FlaskConical size={15} />, t: "Find the gap", d: "Improvement the market missed" },
        ].map((x) => (
          <div key={x.t} className="flex items-start gap-2 text-[11.5px]">
            <span className="mt-0.5 text-faint">{x.icon}</span>
            <div className="leading-tight">
              <p className="text-txt">{x.t}</p>
              <p className="text-faint">{x.d}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-auto rounded-lg border border-hairline bg-canvas/40 p-3">
        <p className="text-xs font-medium text-txt">Singapore universe · 2019–2023</p>
        <p className="mt-0.5 text-[11px] leading-snug text-faint">
          10 SGX large-caps, ranked against a ~50-name ASEAN reference panel. Every number traces to a source.
        </p>
      </div>
    </aside>
  );
}
