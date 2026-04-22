import { useNavigate } from "react-router";
import { useTrolleyStore } from "../../stores/trolley-store";
import { useNotificationStore } from "../../stores/notification-store";

export default function TrolleyTimelineList() {
  const list = useTrolleyStore((s) => s.list);
  const remove = useTrolleyStore((s) => s.remove);
  const duplicate = useTrolleyStore((s) => s.duplicate);
  const notify = useNotificationStore((s) => s.notify);
  const navigate = useNavigate();

  async function handleDuplicate(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    const tl = await duplicate(id);
    notify("success", "Trolley timeline duplicated");
    navigate(`/trolleys/${tl.id}`);
  }

  return (
    <div className="space-y-4">
      {list.map((tl, index) => (
        <div
          key={tl.id}
          className="group flex items-center gap-6 p-4 rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm hover:bg-zinc-800/60 hover:border-white/10 transition-all duration-300 cursor-pointer shadow-lg hover:shadow-xl hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
          style={{ animationDelay: `${index * 50}ms` }}
          onClick={() => navigate(`/trolleys/${tl.id}`)}
        >
          <div className="flex-1 min-w-0">
            <p className="text-xl font-medium text-white tracking-wide truncate group-hover:text-sky-50 transition-colors">
              {tl.name}
            </p>
            <p className="text-sm text-zinc-400 mt-2 flex items-center gap-3">
              <span className="px-2.5 py-0.5 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-sky-300/90 tracking-wider uppercase">
                {tl.duration}s
              </span>
              <span className="text-zinc-600">&bull;</span>
              <span>{tl.events} events</span>
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
          <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300 ml-auto">
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
                notify("info", "Trolley timeline deleted");
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
          <p className="text-zinc-300 text-lg font-medium">No trolley timelines yet</p>
          <p className="text-zinc-500 text-sm mt-2">Create one to drive a trolley's position over time.</p>
        </div>
      )}
    </div>
  );
}
