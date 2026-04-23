import type { ReactNode } from "react";

export type DevicePageAccent = "vents" | "trolley";
export type DevicePageTab = "panel" | "timelines";

const ACCENT: Record<
  DevicePageAccent,
  {
    activeTabBg: string;
    createBtn: string;
    createGlow: string;
    iconFill: string;
  }
> = {
  vents: {
    activeTabBg: "bg-orange-600 text-white",
    createBtn:
      "bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300",
    createGlow:
      "shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)]",
    iconFill: "text-orange-400/80",
  },
  trolley: {
    activeTabBg: "bg-sky-600 text-white",
    createBtn:
      "bg-gradient-to-r from-sky-500 to-sky-400 hover:from-sky-400 hover:to-sky-300",
    createGlow:
      "shadow-[0_0_20px_rgba(56,189,248,0.3)] hover:shadow-[0_0_30px_rgba(56,189,248,0.5)]",
    iconFill: "text-sky-400/80",
  },
};

interface Props {
  title: string;
  subtitle: string;
  accent: DevicePageAccent;
  tab: DevicePageTab;
  onTabChange: (next: DevicePageTab) => void;
  /** Shows a "New Timeline" button under the header when defined and
   *  the Timelines tab is active. */
  onCreate?: () => void;
  createLabel?: string;
  panel: ReactNode;
  timelines: ReactNode;
}

/**
 * Shared shell for the Vents and Trolley device pages — header, tabs,
 * and body switcher. Content per tab is passed in via props so the
 * two pages look identical apart from accent colour + tab content.
 */
export default function DevicePageLayout({
  title,
  subtitle,
  accent,
  tab,
  onTabChange,
  onCreate,
  createLabel = "New Timeline",
  panel,
  timelines,
}: Props) {
  const a = ACCENT[accent];
  const showCreate = tab === "timelines" && onCreate;

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">{title}</h2>
          <p className="text-zinc-400 text-sm">{subtitle}</p>
        </div>
        {showCreate && (
          <button
            onClick={onCreate}
            className={`px-5 py-2.5 ${a.createBtn} rounded-xl text-sm font-semibold text-white ${a.createGlow} transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              {createLabel}
            </span>
          </button>
        )}
      </div>

      <div className="flex gap-2 mb-6">
        <button
          onClick={() => onTabChange("panel")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            tab === "panel"
              ? a.activeTabBg
              : "bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-300"
          }`}
        >
          Test panel
        </button>
        <button
          onClick={() => onTabChange("timelines")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            tab === "timelines"
              ? a.activeTabBg
              : "bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-300"
          }`}
        >
          Timelines
        </button>
      </div>

      {tab === "panel" ? panel : timelines}
    </div>
  );
}
