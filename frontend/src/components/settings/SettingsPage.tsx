import { Moon, Palette, Sun } from "lucide-react";
import { useThemeMode } from "../../theme/ThemeContext";

const OPTIONS = [
  {
    mode: "dark" as const,
    title: "Graphite dark",
    description: "Current dashboard look with deep panels and high-contrast cards.",
    icon: <Moon size={17} />,
  },
  {
    mode: "light" as const,
    title: "Marble light",
    description: "Warm off-white canvas with stone panels and softer borders.",
    icon: <Sun size={17} />,
  },
];

export default function SettingsPage() {
  const { mode, setMode } = useThemeMode();

  return (
    <div className="mx-auto flex h-full w-full max-w-6xl flex-col px-6 py-6 sm:px-10 lg:px-12">
      <header className="pb-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-pos/15 text-pos">
            <Palette size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-txt">Settings</h1>
            <p className="text-sm text-muted">
              Control workspace appearance and dashboard preferences.
            </p>
          </div>
        </div>
      </header>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.55fr)]">
        <div className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-faint">
                Appearance
              </p>
              <h2 className="mt-1 text-xl font-semibold text-txt">
                Theme mode
              </h2>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
                The setting applies across the dashboard, assistant, charts,
                inputs, panels, and sidebar. Dark mode remains the default.
              </p>
            </div>
            <span className="rounded-full border border-hairline bg-raised px-3 py-1 text-xs font-medium text-muted">
              {mode === "dark" ? "Dark active" : "Light active"}
            </span>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {OPTIONS.map((option) => {
              const active = mode === option.mode;
              return (
                <button
                  key={option.mode}
                  onClick={() => setMode(option.mode)}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? "border-pos bg-pos/10 text-txt"
                      : "border-hairline bg-canvas/50 text-muted hover:bg-raised hover:text-txt"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className={active ? "text-pos" : "text-faint"}>
                      {option.icon}
                    </span>
                    <span className="font-semibold">{option.title}</span>
                  </span>
                  <span className="mt-2 block text-sm leading-relaxed text-muted">
                    {option.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-2xl border border-hairline bg-surface p-5 shadow-panel">
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">
            Preview
          </p>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-hairline bg-canvas/60 p-4">
              <p className="text-sm font-semibold text-txt">Dashboard card</p>
              <p className="mt-1 text-sm text-muted">
                Surfaces, borders, and text adapt from shared theme tokens.
              </p>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-raised">
                <div className="h-full w-2/3 rounded-full bg-pos" />
              </div>
            </div>
            <div className="rounded-xl bg-pos px-4 py-3 text-sm font-medium text-canvas">
              User chat bubble uses a solid accent color.
            </div>
            <div className="rounded-xl border border-hairline bg-raised px-4 py-3 text-sm text-txt">
              Assistant panels stay readable in both modes.
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
