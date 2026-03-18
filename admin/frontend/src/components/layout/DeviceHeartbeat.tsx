import { useDeviceStore } from "../../stores/device-store";
import { usePlaybackStore } from "../../stores/playback-store";

export default function DeviceHeartbeat() {
  const devices = useDeviceStore((s) => s.list);
  const statuses = useDeviceStore((s) => s.deviceStatuses);
  const playing = usePlaybackStore((s) => s.status.playing);

  if (devices.length === 0) {
    return <div className="text-[10px] text-zinc-600 px-3">No devices</div>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {devices.map((device) => {
        const online = statuses[device.id] ?? false;
        return (
          <div
            key={device.id}
            className="flex items-center justify-between px-3 py-1.5 rounded-md border border-zinc-800/50 bg-zinc-900/30"
            title={`${device.name} (${device.ip_address})`}
          >
            <span className="text-[11px] text-zinc-400 font-mono truncate mr-2">
              {device.name}
            </span>
            <div className="flex items-center gap-1.5">
              {/* TX indicator */}
              <div
                className={`w-1.5 h-1.5 rounded-full transition-all duration-75 ${
                  playing
                    ? "bg-orange-400 shadow-[0_0_4px_rgba(249,115,22,0.6)]"
                    : "bg-zinc-700"
                }`}
                title="TX"
              />
              <div className="w-1.5 h-px bg-zinc-700" />
              {/* RX indicator */}
              <div
                className={`w-1.5 h-1.5 rounded-full transition-all duration-75 ${
                  online
                    ? "bg-green-400 shadow-[0_0_4px_rgba(74,222,128,0.6)]"
                    : "bg-red-500/80"
                }`}
                title={online ? "Online" : "Offline"}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
