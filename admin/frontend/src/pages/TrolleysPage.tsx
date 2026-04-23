import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useTrolleyStore } from "../stores/trolley-store";
import { useDeviceStore } from "../stores/device-store";
import DevicePageLayout, {
  type DevicePageTab,
} from "../components/device-page/DevicePageLayout";
import EmptyDevicesState from "../components/device-page/EmptyDevicesState";
import TrolleyTimelineList from "../components/trolley/TrolleyTimelineList";
import TrolleyTestPanel from "../components/trolley/TrolleyTestPanel";

export default function TrolleysPage() {
  const navigate = useNavigate();
  const fetchTimelines = useTrolleyStore((s) => s.fetchList);
  const createTrolleyTimeline = useTrolleyStore((s) => s.createTrolleyTimeline);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const [tab, setTab] = useState<DevicePageTab>("panel");

  useEffect(() => {
    fetchTimelines();
    fetchDevices();
  }, [fetchTimelines, fetchDevices]);

  const trolleys = devices.filter((d) => d.type === "trolley");

  async function handleCreate() {
    const tl = await createTrolleyTimeline({ name: "New Trolley Timeline", duration: 60 });
    navigate(`/trolleys/${tl.id}`);
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
      timelines={<TrolleyTimelineList />}
    />
  );
}
