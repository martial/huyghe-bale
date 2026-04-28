import type { Device } from "../../types/device";
import { useVentsStatus } from "../../hooks/use-vents-status";
import { useDeviceStore } from "../../stores/device-store";
import DeviceControlCard from "../device-page/DeviceControlCard";
import VentsHero from "./VentsHero";
import VentsTestPanel from "./VentsTestPanel";
import VentsAlarmBadge from "./VentsAlarmBadge";
import VentsConfigPanel from "./VentsConfigPanel";

/**
 * Single vents device: hero status block + raw-control panel. Same
 * shape as the inline `VentsHeroSlot` that DeviceCard uses, extracted
 * so the /vents page can reuse it without duplicating the status-hook
 * wiring.
 */
export default function VentsDeviceControl({ device }: { device: Device }) {
  const { status, stale, lastPushAgeS } = useVentsStatus(device.id);
  const alarms = useDeviceStore((s) => s.deviceAlarms[device.id]);
  return (
    <DeviceControlCard device={device}>
      <div className="space-y-4">
        {alarms && alarms.active.length > 0 && <VentsAlarmBadge alarms={alarms} />}
        <VentsHero status={status} stale={stale} lastPushAgeS={lastPushAgeS} />
        <VentsConfigPanel status={status} rpmAlarmThreshold={alarms?.threshold} />
        <VentsTestPanel device={device} status={status} />
      </div>
    </DeviceControlCard>
  );
}
