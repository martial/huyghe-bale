import { useDeviceStore } from "../../stores/device-store";

export default function DeviceHeartbeat() {
  const devices = useDeviceStore((s) => s.list);
  const statuses = useDeviceStore((s) => s.deviceStatuses);
  const loading = useDeviceStore((s) => s.loading);

  if (loading && devices.length === 0) {
    return (
      <div className="flex flex-col gap-1.5">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-zinc-800/50 bg-zinc-900/30 animate-pulse"
          >
            <div className="w-2 h-2 rounded-full bg-zinc-700" />
            <div className="h-2.5 w-20 rounded bg-zinc-800/80" />
          </div>
        ))}
      </div>
    );
  }

  if (devices.length === 0) {
    return <div className="text-[10px] text-zinc-600 px-3">No devices</div>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {devices.map((device) => {
        const needsRepair = device.needs_repair;
        const online = statuses[device.id] === "online";
        const label = device.name && !needsRepair
          ? device.name
          : `${device.id.replace(/^dev_/, "")} (repair)`;
        const tooltip = needsRepair
          ? `Missing: ${(device.missing_fields || []).join(", ")} — open Devices to fix`
          : `${device.name} (${device.ip_address})`;

        return (
          <div
            key={device.id}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${
              needsRepair
                ? "border-yellow-500/30 bg-yellow-500/5"
                : "border-zinc-800/50 bg-zinc-900/30"
            }`}
            title={tooltip}
          >
            <div className="relative flex items-center justify-center w-2.5 h-2.5">
              {online && !needsRepair && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-green-400/40 animate-ping" />
              )}
              <div
                className={`relative w-2 h-2 rounded-full ${
                  needsRepair
                    ? "bg-yellow-400 shadow-[0_0_6px_rgba(250,204,21,0.5)]"
                    : online
                    ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]"
                    : "bg-zinc-600"
                }`}
              />
            </div>
            <span className={`text-[11px] font-mono truncate ${
              needsRepair ? "text-yellow-300/80" : "text-zinc-400"
            }`}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
