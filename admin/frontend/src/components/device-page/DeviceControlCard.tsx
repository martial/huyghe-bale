import type { ReactNode } from "react";
import type { Device } from "../../types/device";
import { useDeviceStore } from "../../stores/device-store";

interface Props {
  device: Device;
  children: ReactNode;
  /** Optional right-aligned header content (actions, secondary info). */
  headerRight?: ReactNode;
}

/**
 * Card shell for a single-device test panel. Shows a status dot, the
 * device name, and IP:port as the card header, then renders `children`
 * as the body. Keeps the VentsDeviceControl and TrolleyTestPanel
 * visually aligned without each having to hand-roll the chrome.
 */
export default function DeviceControlCard({ device, children, headerRight }: Props) {
  const online = useDeviceStore((s) => s.deviceStatuses[device.id] === "online");

  return (
    <div className="rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm shadow-lg overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-white/5 bg-white/[0.02]">
        <span
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            online
              ? "bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]"
              : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"
          }`}
          title={online ? "online" : "offline"}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-100 truncate">
            {device.name || "(unnamed device)"}
          </p>
          <p className="text-[11px] text-zinc-500 font-mono truncate">
            {device.ip_address || "—"}:{device.osc_port}
          </p>
        </div>
        {headerRight}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}
