import { useNavigate } from "react-router";
import type { UniversalTimelineSummary } from "./types";
import Preview from "./Preview";

interface Props {
  items: UniversalTimelineSummary[];
  /** Route prefix used when a row is clicked (e.g. "/timelines" or
   *  "/trolleys"). The summary id is appended. */
  routePrefix: string;
  /** Empty-state message when `items` is empty. */
  emptyTitle: string;
  emptySubtitle?: string;
  /** Actions exposed per-row. Each receives the row id. */
  onDuplicate: (id: string) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
  /** Accent colour used on the duration pill / hover text. */
  accent: "vents" | "trolley";
}

const ACCENT_PILL: Record<Props["accent"], string> = {
  vents: "text-orange-400/90 group-hover:text-orange-50",
  trolley: "text-sky-300/90 group-hover:text-sky-50",
};

/**
 * Unified timeline list — grid of preview + metadata cards. Handles both
 * vents and trolley timelines via the UniversalTimelineSummary shape.
 * Duplicate / Delete actions are injected; readonly rows hide Delete.
 */
export default function List({
  items,
  routePrefix,
  emptyTitle,
  emptySubtitle,
  onDuplicate,
  onDelete,
  accent,
}: Props) {
  const navigate = useNavigate();

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20 mt-8">
        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-5 border border-white/10 shadow-inner">
          <svg className="w-8 h-8 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <p className="text-zinc-300 text-lg font-medium">{emptyTitle}</p>
        {emptySubtitle && (
          <p className="text-zinc-500 text-sm mt-2">{emptySubtitle}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((tl, index) => (
        <div
          key={tl.id}
          className="group flex flex-col sm:flex-row sm:items-center gap-6 p-4 rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm hover:bg-zinc-800/60 hover:border-white/10 transition-all duration-300 cursor-pointer shadow-lg hover:shadow-xl hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
          style={{ animationDelay: `${index * 50}ms` }}
          onClick={() => navigate(`${routePrefix}/${tl.id}`)}
        >
          <div className="w-full sm:w-48 h-24 rounded-xl overflow-hidden shadow-inner border border-white/5 bg-black/40 flex-shrink-0 relative group-hover:shadow-[0_0_20px_rgba(249,115,22,0.15)] transition-all duration-300">
            <Preview id={tl.id} kind={tl.kind} />
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-xl font-medium text-white tracking-wide truncate group-hover:text-white transition-colors flex items-center gap-2">
              {tl.name}
              {tl.readonly && (
                <span
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border bg-amber-500/10 text-amber-300 border-amber-500/30"
                  title="Built-in example — duplicate to edit"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.75}
                      d="M12 11c.5 0 1-.2 1.4-.6.4-.4.6-.9.6-1.4 0-.5-.2-1-.6-1.4a2 2 0 00-2.8 0c-.4.4-.6.9-.6 1.4 0 .5.2 1 .6 1.4.4.4.9.6 1.4.6zM5 11V7a7 7 0 0114 0v4M5 11h14a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2z"
                    />
                  </svg>
                  example
                </span>
              )}
            </p>
            <p className="text-sm text-zinc-400 mt-2 flex items-center gap-3">
              <span
                className={`px-2.5 py-0.5 rounded-full bg-white/5 border border-white/10 text-xs font-medium ${ACCENT_PILL[accent]} tracking-wider uppercase`}
              >
                {tl.duration}s
              </span>
              <span className="text-zinc-600">&bull;</span>
              <span>
                {tl.eventCount} {tl.kind === "vents" ? "interpolation points" : "events"}
              </span>
              {tl.created_at && (
                <>
                  <span className="text-zinc-600">&bull;</span>
                  <span className="text-zinc-500 text-xs">
                    Added {new Date(tl.created_at).toLocaleDateString()}
                  </span>
                </>
              )}
            </p>
          </div>

          <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300 sm:ml-auto">
            <button
              onClick={async (e) => {
                e.stopPropagation();
                await onDuplicate(tl.id);
              }}
              className="text-sm font-semibold text-zinc-300 hover:text-white bg-white/5 hover:bg-white/10 px-4 py-2.5 rounded-xl transition-all shadow-sm"
            >
              Duplicate
            </button>
            {!tl.readonly && (
              <button
                onClick={async (e) => {
                  e.stopPropagation();
                  await onDelete(tl.id);
                }}
                className="text-sm font-semibold text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 px-4 py-2.5 rounded-xl transition-all shadow-sm"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
