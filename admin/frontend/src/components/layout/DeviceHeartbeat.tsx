import { useDeviceStore } from "../../stores/device-store";

export default function DeviceHeartbeat() {
  const devices = useDeviceStore((s) => s.list);
  const statuses = useDeviceStore((s) => s.deviceStatuses);

  if (devices.length === 0) {
    return <div className="text-[10px] text-zinc-600 px-3">No devices</div>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {devices.map((device) => {
        const online = statuses[device.id] === "online";
        return (
          <div
            key={device.id}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-zinc-800/50 bg-zinc-900/30"
            title={`${device.name} (${device.ip_address})`}
          >
            <div className="relative flex items-center justify-center w-2.5 h-2.5">
              {online && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-green-400/40 animate-ping" />
              )}
              <div
                className={`relative w-2 h-2 rounded-full ${
                  online
                    ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]"
                    : "bg-zinc-600"
                }`}
              />
            </div>
            <span className="text-[11px] text-zinc-400 font-mono truncate">
              {device.name}
            </span>
          </div>
        );
      })}
    </div>
  );
}
