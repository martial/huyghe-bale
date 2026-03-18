import { useNavigate } from "react-router";
import { useTimelineStore } from "../../stores/timeline-store";
import { useNotificationStore } from "../../stores/notification-store";
import TimelinePreview from "./TimelinePreview";

export default function TimelineList() {
  const list = useTimelineStore((s) => s.list);
  const remove = useTimelineStore((s) => s.remove);
  const duplicate = useTimelineStore((s) => s.duplicate);
  const notify = useNotificationStore((s) => s.notify);
  const navigate = useNavigate();

  async function handleDuplicate(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    const tl = await duplicate(id);
    notify("success", "Timeline duplicated successfully");
    navigate(`/timelines/${tl.id}`);
  }

  return (
    <div className="space-y-4">
      {list.map((tl, index) => (
        <div
          key={tl.id}
          className="group flex flex-col sm:flex-row sm:items-center gap-6 p-4 rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm hover:bg-zinc-800/60 hover:border-white/10 transition-all duration-300 cursor-pointer shadow-lg hover:shadow-xl hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
          style={{ animationDelay: `${index * 50}ms` }}
          onClick={() => navigate(`/timelines/${tl.id}`)}
        >
          <div className="w-full sm:w-48 h-24 rounded-xl overflow-hidden shadow-inner border border-white/5 bg-black/40 flex-shrink-0 relative group-hover:shadow-[0_0_20px_rgba(249,115,22,0.15)] transition-all duration-300">
            <TimelinePreview timelineId={tl.id} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xl font-medium text-white tracking-wide truncate group-hover:text-orange-50 transition-colors">{tl.name}</p>
            <p className="text-sm text-zinc-400 mt-2 flex items-center gap-3">
              <span className="px-2.5 py-0.5 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-orange-400/90 tracking-wider uppercase">
                {tl.duration}s
              </span>
              <span className="text-zinc-600">&bull;</span> 
              <span>{tl.lane_a_points + tl.lane_b_points} interpolation points</span>
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
              onClick={(e) => handleDuplicate(e, tl.id)}
              className="text-sm font-semibold text-zinc-300 hover:text-white bg-white/5 hover:bg-white/10 px-4 py-2.5 rounded-xl transition-all shadow-sm"
            >
              Duplicate
            </button>
            <button
              onClick={(e) => { 
                e.stopPropagation(); 
                remove(tl.id); 
                notify("info", "Timeline deleted");
              }}
              className="text-sm font-semibold text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 px-4 py-2.5 rounded-xl transition-all shadow-sm"
            >
              Delete
            </button>
          </div>
        </div>
      ))}

      {!list.length && (
        <div className="flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20 mt-8">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-5 border border-white/10 shadow-inner">
            <svg className="w-8 h-8 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          </div>
          <p className="text-zinc-300 text-lg font-medium">No timelines configured yet</p>
          <p className="text-zinc-500 text-sm mt-2">Create your first timeline to start orchestrating events.</p>
        </div>
      )}
    </div>
  );
}
