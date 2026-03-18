import { useEffect } from "react";
import { useNavigate, Link } from "react-router";
import { useOrchestrationStore } from "../stores/orchestration-store";
import { useNotificationStore } from "../stores/notification-store";

export default function OrchestrationsPage() {
  const navigate = useNavigate();
  const list = useOrchestrationStore((s) => s.list);
  const fetchList = useOrchestrationStore((s) => s.fetchList);
  const createOrchestration = useOrchestrationStore((s) => s.createOrchestration);
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
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-zinc-100">Orchestrations</h2>
        <button
          onClick={handleCreate}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-500 rounded-lg text-sm font-medium transition-all duration-200"
        >
          + New Orchestration
        </button>
      </div>

      <div className="space-y-2">
        {list.map((orch) => (
          <Link
            key={orch.id}
            to={`/orchestrations/${orch.id}`}
            className="block p-4 rounded-xl border border-zinc-800/50 bg-zinc-900/80 hover:border-zinc-600/50 transition-all duration-200 shadow-sm hover:scale-[1.01]"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-zinc-200">{orch.name}</p>
                <p className="text-xs text-zinc-500 mt-1">
                  {orch.steps?.length || 0} step(s)
                  {orch.loop && <span className="ml-2 text-orange-400">looping</span>}
                </p>
              </div>
              <span className="text-zinc-600 text-xs font-mono">{orch.id}</span>
            </div>
          </Link>
        ))}
      </div>

      {!list.length && (
        <p className="text-zinc-500 text-sm mt-8 text-center">No orchestrations yet.</p>
      )}
    </div>
  );
}
