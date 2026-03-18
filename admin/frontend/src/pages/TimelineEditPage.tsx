import { useEffect } from "react";
import { useParams } from "react-router";
import { useTimelineStore } from "../stores/timeline-store";
import TimelineEditor from "../components/timeline/TimelineEditor";

export default function TimelineEditPage() {
  const { id } = useParams<{ id: string }>();
  const current = useTimelineStore((s) => s.current);
  const loading = useTimelineStore((s) => s.loading);
  const fetchOne = useTimelineStore((s) => s.fetchOne);

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
      <div className="h-full flex items-center justify-center text-zinc-500">Timeline not found</div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <TimelineEditor timeline={current} />
    </div>
  );
}
