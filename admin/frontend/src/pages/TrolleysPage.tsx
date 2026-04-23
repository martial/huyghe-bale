import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useTrolleyStore } from "../stores/trolley-store";
import { useDeviceStore } from "../stores/device-store";
import { useNotificationStore } from "../stores/notification-store";
import DevicePageLayout, {
  type DevicePageTab,
} from "../components/device-page/DevicePageLayout";
import EmptyDevicesState from "../components/device-page/EmptyDevicesState";
import TrolleyTestPanel from "../components/trolley/TrolleyTestPanel";
import { List as TimelineList } from "../timeline-lib";
import { trolleySummaryToUniversal } from "../timeline-lib/adapters/trolley";

export default function TrolleysPage() {
  const navigate = useNavigate();
  const trolleyTimelines = useTrolleyStore((s) => s.list);
  const fetchTimelines = useTrolleyStore((s) => s.fetchList);
  const createTrolleyTimeline = useTrolleyStore((s) => s.createTrolleyTimeline);
  const duplicateTimeline = useTrolleyStore((s) => s.duplicate);
  const removeTimeline = useTrolleyStore((s) => s.remove);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const notify = useNotificationStore((s) => s.notify);
  const [tab, setTab] = useState<DevicePageTab>("panel");

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  const trolleys = devices.filter((d) => d.type === "trolley");

  const timelineSummaries = useMemo(
    () => trolleyTimelines.map(trolleySummaryToUniversal),
    [trolleyTimelines],
  );

  async function handleCreate() {
    const tl = await createTrolleyTimeline({ name: "New Trolley Timeline", duration: 60 });
    navigate(`/trolleys/${tl.id}`);
  }

  async function handleDuplicate(id: string) {
    const tl = await duplicateTimeline(id);
    notify("success", "Trolley timeline duplicated");
    navigate(`/trolleys/${tl.id}`);
  }

  async function handleDelete(id: string) {
    await removeTimeline(id);
    notify("info", "Trolley timeline deleted");
  }

  const panel = (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {trolleys.length === 0 ? (
        <EmptyDevicesState deviceTypeLabel="trolley" deviceTypeValue="trolley" />
      ) : (
        trolleys.map((d) => <TrolleyTestPanel key={d.id} device={d} />)
      )}
    </div>
  );

  return (
    <DevicePageLayout
      title="Trolleys"
      subtitle="Test panel &amp; position timelines for trolley devices"
      accent="trolley"
      tab={tab}
      onTabChange={setTab}
      onCreate={handleCreate}
      panel={panel}
      timelines={
        <TimelineList
          items={timelineSummaries}
          routePrefix="/trolleys"
          accent="trolley"
          emptyTitle="No trolley timelines yet"
          emptySubtitle="Create one to drive a trolley's position over time."
          onDuplicate={handleDuplicate}
          onDelete={handleDelete}
        />
      }
    />
  );
}
