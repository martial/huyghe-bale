import { useEffect } from "react";
import { useParams } from "react-router";
import { useTrolleyStore } from "../stores/trolley-store";
import TrolleyEditor from "../components/trolley/TrolleyEditor";

export default function TrolleyEditPage() {
  const { id } = useParams<{ id: string }>();
  const current = useTrolleyStore((s) => s.current);
  const loading = useTrolleyStore((s) => s.loading);
  const fetchOne = useTrolleyStore((s) => s.fetchOne);

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
      <div className="h-full flex items-center justify-center text-zinc-500">
        Trolley timeline not found
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <TrolleyEditor timeline={current} />
    </div>
  );
}
