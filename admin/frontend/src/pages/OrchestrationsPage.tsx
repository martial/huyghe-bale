import { useEffect } from "react";
import { useNavigate } from "react-router";
import { useOrchestrationStore } from "../stores/orchestration-store";
import { useNotificationStore } from "../stores/notification-store";

export default function OrchestrationsPage() {
  const navigate = useNavigate();
  const list = useOrchestrationStore((s) => s.list);
  const fetchList = useOrchestrationStore((s) => s.fetchList);
  const createOrchestration = useOrchestrationStore((s) => s.createOrchestration);
  const remove = useOrchestrationStore((s) => s.remove);
  const notify = useNotificationStore((s) => s.notify);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  async function handleCreate() {
    const orch = await createOrchestration({ name: "New Orchestration" });
    notify("success", "Orchestration created");
    navigate(`/orchestrations/${orch.id}`);
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex items-center justify-between mb-10 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Orchestrations</h2>
          <p className="text-zinc-400 text-sm">Sequence timelines across devices</p>
        </div>
        <button
          onClick={handleCreate}
          className="px-5 py-2.5 bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300 rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
        >
          <span className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            New Orchestration
          </span>
        </button>
      </div>

      <div className="space-y-4">
        {list.map((orch, index) => (
          <div
            key={orch.id}
            className="group flex items-center gap-6 p-4 rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm hover:bg-zinc-800/60 hover:border-white/10 transition-all duration-300 cursor-pointer shadow-lg hover:shadow-xl hover:-translate-y-1 animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
            style={{ animationDelay: `${index * 50}ms` }}
            onClick={() => navigate(`/orchestrations/${orch.id}`)}
          >
            <div className="flex-1 min-w-0">
              <p className="text-xl font-medium text-white tracking-wide truncate group-hover:text-orange-50 transition-colors">{orch.name}</p>
              <p className="text-sm text-zinc-400 mt-2 flex items-center gap-3">
                <span>{orch.steps?.length || 0} step(s)</span>
                {orch.loop && (
                  <>
                    <span className="text-zinc-600">&bull;</span>
                    <span className="px-2.5 py-0.5 rounded-full bg-white/5 border border-white/10 text-xs font-medium text-orange-400/90 tracking-wider uppercase">
                      looping
                    </span>
                  </>
                )}
              </p>
            </div>
            <span className="text-zinc-600 text-xs font-mono">{orch.id}</span>
            <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  remove(orch.id);
                  notify("info", "Orchestration deleted");
                }}
                className="text-sm font-semibold text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 px-4 py-2.5 rounded-xl transition-all shadow-sm"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {!list.length && (
        <div className="flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20 mt-8">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-5 border border-white/10 shadow-inner">
            <svg className="w-8 h-8 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3l-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3l-3 3" /></svg>
          </div>
          <p className="text-zinc-300 text-lg font-medium">No orchestrations yet</p>
          <p className="text-zinc-500 text-sm mt-2">Create your first orchestration to sequence timelines across devices.</p>
        </div>
      )}
    </div>
  );
}
