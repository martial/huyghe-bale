import { useEffect, useMemo } from "react";
import { useParams } from "react-router";
import { useTrolleyStore } from "../stores/trolley-store";
import { useNotificationStore } from "../stores/notification-store";
import { Editor } from "../timeline-lib";
import {
  trolleyTimelineToUniversal,
  universalToTrolleyTimeline,
} from "../timeline-lib/adapters/trolley";
import type { UniversalTimeline } from "../timeline-lib/types";

export default function TrolleyEditPage() {
  const { id } = useParams<{ id: string }>();
  const current = useTrolleyStore((s) => s.current);
  const loading = useTrolleyStore((s) => s.loading);
  const fetchOne = useTrolleyStore((s) => s.fetchOne);
  const save = useTrolleyStore((s) => s.save);
  const saveSilent = useTrolleyStore((s) => s.saveSilent);
  const notify = useNotificationStore((s) => s.notify);

  useEffect(() => {
    if (id) fetchOne(id);
  }, [id, fetchOne]);

  const universal = useMemo(
    () => (current ? trolleyTimelineToUniversal(current) : null),
    [current],
  );

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">Loading...</div>
    );
  }
  if (!universal) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">
        Trolley timeline not found
      </div>
    );
  }

  async function handleAutoSave(next: UniversalTimeline) {
    await saveSilent(universalToTrolleyTimeline(next));
  }

  async function handleSave(next: UniversalTimeline) {
    await save(universalToTrolleyTimeline(next));
    notify("success", "Trolley timeline saved");
  }

  return (
    <div className="h-full flex flex-col">
      <Editor
        timeline={universal}
        onChange={handleAutoSave}
        onSave={handleSave}
        backPath="/trolleys"
      />
    </div>
  );
}
