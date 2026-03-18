import { useEffect } from "react";
import { useParams } from "react-router";
import { useOrchestrationStore } from "../stores/orchestration-store";
import OrchestrationEditor from "../components/orchestration/OrchestrationEditor";

export default function OrchestrationEditPage() {
  const { id } = useParams<{ id: string }>();
  const current = useOrchestrationStore((s) => s.current);
  const loading = useOrchestrationStore((s) => s.loading);
  const fetchOne = useOrchestrationStore((s) => s.fetchOne);

  useEffect(() => {
    if (id) fetchOne(id);
  }, [id, fetchOne]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">Loading...</div>
    );
  }

  if (!current) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">Orchestration not found</div>
    );
  }

  return <OrchestrationEditor orchestration={current} />;
}
