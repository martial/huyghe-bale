import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useTimelineStore } from "../stores/timeline-store";
import { useDeviceStore } from "../stores/device-store";
import DevicePageLayout, {
  type DevicePageTab,
} from "../components/device-page/DevicePageLayout";
import EmptyDevicesState from "../components/device-page/EmptyDevicesState";
import VentsDeviceControl from "../components/device/VentsDeviceControl";
import TimelineList from "../components/timeline/TimelineList";

export default function VentsPage() {
  const navigate = useNavigate();
  const fetchTimelines = useTimelineStore((s) => s.fetchList);
  const createTimeline = useTimelineStore((s) => s.createTimeline);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const [tab, setTab] = useState<DevicePageTab>("panel");

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  const vents = devices.filter((d) => (d.type ?? "vents") === "vents");

  async function handleCreate() {
    const tl = await createTimeline({ name: "New Timeline", duration: 60 });
    navigate(`/timelines/${tl.id}`);
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
      timelines={<TimelineList />}
    />
  );
}
