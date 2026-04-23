import { useEffect, useMemo } from "react";
import { useParams } from "react-router";
import { useTimelineStore } from "../stores/timeline-store";
import { useNotificationStore } from "../stores/notification-store";
import { Editor } from "../timeline-lib";
import {
  ventsTimelineToUniversal,
  universalToVentsTimeline,
} from "../timeline-lib/adapters/vents";
import type { UniversalTimeline } from "../timeline-lib/types";

export default function TimelineEditPage() {
  const { id } = useParams<{ id: string }>();
  const current = useTimelineStore((s) => s.current);
  const loading = useTimelineStore((s) => s.loading);
  const fetchOne = useTimelineStore((s) => s.fetchOne);
  const save = useTimelineStore((s) => s.save);
  const saveSilent = useTimelineStore((s) => s.saveSilent);
  const notify = useNotificationStore((s) => s.notify);

  useEffect(() => {
    if (id) fetchOne(id);
  }, [id, fetchOne]);

  const universal = useMemo(
    () => (current ? ventsTimelineToUniversal(current) : null),
    [current],
  );

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">Loading...</div>
    );
  }
  if (!universal) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">Timeline not found</div>
    );
  }

  async function handleAutoSave(next: UniversalTimeline) {
    await saveSilent(universalToVentsTimeline(next));
  }

  async function handleSave(next: UniversalTimeline) {
    await save(universalToVentsTimeline(next));
    notify("success", "Timeline saved");
  }

  return (
    <div className="h-full flex flex-col">
      <Editor
        timeline={universal}
        onChange={handleAutoSave}
        onSave={handleSave}
        backPath="/vents"
      />
    </div>
  );
}
