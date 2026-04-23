import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useTimelineStore } from "../stores/timeline-store";
import { useDeviceStore } from "../stores/device-store";
import { useNotificationStore } from "../stores/notification-store";
import DevicePageLayout, {
  type DevicePageTab,
} from "../components/device-page/DevicePageLayout";
import EmptyDevicesState from "../components/device-page/EmptyDevicesState";
import VentsDeviceControl from "../components/device/VentsDeviceControl";
import { List as TimelineList } from "../timeline-lib";
import { ventsSummaryToUniversal } from "../timeline-lib/adapters/vents";

export default function VentsPage() {
  const navigate = useNavigate();
  const timelines = useTimelineStore((s) => s.list);
  const fetchTimelines = useTimelineStore((s) => s.fetchList);
  const createTimeline = useTimelineStore((s) => s.createTimeline);
  const duplicateTimeline = useTimelineStore((s) => s.duplicate);
  const removeTimeline = useTimelineStore((s) => s.remove);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const notify = useNotificationStore((s) => s.notify);
  const [tab, setTab] = useState<DevicePageTab>("panel");

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  const vents = devices.filter((d) => (d.type ?? "vents") === "vents");

  const timelineSummaries = useMemo(
    () => timelines.map(ventsSummaryToUniversal),
    [timelines],
  );

  async function handleCreate() {
    const tl = await createTimeline({ name: "New Timeline", duration: 60 });
    navigate(`/timelines/${tl.id}`);
  }

  async function handleDuplicate(id: string) {
    const tl = await duplicateTimeline(id);
    notify("success", "Timeline duplicated");
    navigate(`/timelines/${tl.id}`);
  }

  async function handleDelete(id: string) {
    await removeTimeline(id);
    notify("info", "Timeline deleted");
  }

  const panel = (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {vents.length === 0 ? (
        <EmptyDevicesState deviceTypeLabel="vents" deviceTypeValue="vents" />
      ) : (
        vents.map((d) => <VentsDeviceControl key={d.id} device={d} />)
      )}
    </div>
  );

  return (
    <DevicePageLayout
      title="Vents"
      subtitle="Thermal control panel &amp; fan timelines for vents devices"
      accent="vents"
      tab={tab}
      onTabChange={setTab}
      onCreate={handleCreate}
      panel={panel}
      timelines={
        <TimelineList
          items={timelineSummaries}
          routePrefix="/timelines"
          accent="vents"
          emptyTitle="No timelines configured yet"
          emptySubtitle="Create your first timeline to start orchestrating events."
          onDuplicate={handleDuplicate}
          onDelete={handleDelete}
        />
      }
    />
  );
}
