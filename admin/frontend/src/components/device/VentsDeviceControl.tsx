import type { Device } from "../../types/device";
import { useVentsStatus } from "../../hooks/use-vents-status";
import DeviceControlCard from "../device-page/DeviceControlCard";
import VentsHero from "./VentsHero";
import VentsTestPanel from "./VentsTestPanel";

/**
 * Single vents device: hero status block + raw-control panel. Same
 * shape as the inline `VentsHeroSlot` that DeviceCard uses, extracted
 * so the /vents page can reuse it without duplicating the status-hook
 * wiring.
 */
export default function VentsDeviceControl({ device }: { device: Device }) {
  const { status, stale, lastPushAgeS } = useVentsStatus(device.id);
  return (
    <DeviceControlCard device={device}>
      <div className="space-y-4">
        <VentsHero status={status} stale={stale} lastPushAgeS={lastPushAgeS} />
        <VentsTestPanel device={device} status={status} />
      </div>
    </DeviceControlCard>
  );
}
