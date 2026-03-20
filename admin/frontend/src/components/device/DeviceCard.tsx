import { useState } from "react";
import type { Device } from "../../types/device";
import { useDeviceStore } from "../../stores/device-store";
import { useNotificationStore } from "../../stores/notification-store";

export default function DeviceCard({ device }: { device: Device }) {
  const update = useDeviceStore((s) => s.update);
  const remove = useDeviceStore((s) => s.remove);
  const ping = useDeviceStore((s) => s.ping);
  const updateSoftware = useDeviceStore((s) => s.updateSoftware);
  const notify = useNotificationStore((s) => s.notify);
  const isOnline = useDeviceStore((s) => s.deviceStatuses[device.id] === "online");
  const deviceVersion = useDeviceStore((s) => s.deviceVersions[device.id]);
  const latestVersion = useDeviceStore((s) => s.latestVersion);
  const isUpdating = useDeviceStore((s) => s.updatingDevices.has(device.id));
  const isRestarting = useDeviceStore((s) => s.restartingDevices.has(device.id));
  const updateLog = useDeviceStore((s) => s.updateLogs[device.id]);
  const systemInfo = useDeviceStore((s) => s.deviceSystemInfo[device.id]);

  const isOutdated = isOnline && deviceVersion && latestVersion && deviceVersion.version !== latestVersion.hash;

  const [pingStatus, setPingStatus] = useState<"idle" | "pinging" | "ok" | "error">("idle");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ ...device });
  const [showLogs, setShowLogs] = useState(false);

  async function handlePing() {
    try {
      setPingStatus("pinging");
      const result = await ping(device.id);
      if (result.ok) {
        setPingStatus("ok");
        notify("success", `Ping OK: ${device.name}`);
      } else {
        setPingStatus("error");
        notify("error", `Ping failed: ${device.name}`);
      }
    } catch {
      setPingStatus("error");
      notify("error", `Ping error: ${device.name}`);
    }
    setTimeout(() => setPingStatus("idle"), 3000);
  }

  async function handleUpdate() {
    await updateSoftware(device.id);
    setShowLogs(true);
  }

  async function handleSave() {
    await update(form as Device);
    notify("success", "Device updated successfully");
    setEditing(false);
  }

  return (
    <div className="p-5 rounded-xl border border-zinc-800/50 bg-zinc-900/80 shadow-sm transition-all duration-200 hover:border-zinc-700/50">
      {!editing ? (
        <>
          <div className="flex items-start justify-between">
            <div>
              <p className="font-medium text-zinc-200">{device.name}</p>
              <p className="text-xs text-zinc-500 font-mono mt-1">
                {device.ip_address}:{device.osc_port}
              </p>
            </div>
            <div className="relative flex h-2 w-2 items-center justify-center">
              {pingStatus === "pinging" && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-75 animate-subtle-ping"></span>
              )}
              <div
                className={`relative inline-flex w-2 h-2 rounded-full transition-colors ${
                  pingStatus === "ok" || isOnline
                    ? "bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]"
                    : pingStatus === "error" || !isOnline
                      ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"
                      : "bg-zinc-600"
                }`}
              />
            </div>
          </div>

          {/* Version info */}
          {(isRestarting || (isOnline && !deviceVersion)) && (
            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-zinc-800 text-[10px] font-mono text-zinc-500 border border-zinc-700/50">
                <span className="inline-block w-2.5 h-2.5 border border-zinc-500 border-t-transparent rounded-full animate-spin" />
                {isRestarting ? "Restarting service..." : "Fetching version..."}
              </span>
            </div>
          )}
          {!isRestarting && isOnline && deviceVersion && (
            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded bg-zinc-800 text-[10px] font-mono text-zinc-400 border border-zinc-700/50">
                {deviceVersion.version}
              </span>
              {isOutdated ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-orange-500/10 text-[10px] font-medium text-orange-400 border border-orange-500/20">
                  Update available
                </span>
              ) : latestVersion && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-green-500/10 text-[10px] font-medium text-green-400 border border-green-500/20">
                  Up to date
                </span>
              )}
            </div>
          )}

          {/* System info */}
          {isOnline && systemInfo && (
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono text-zinc-500">
              <span className="text-zinc-600">Model</span>
              <span className="text-zinc-400 truncate">{systemInfo.model}</span>
              <span className="text-zinc-600">OS</span>
              <span className="text-zinc-400 truncate">{systemInfo.os}</span>
              <span className="text-zinc-600">Python</span>
              <span className="text-zinc-400">{systemInfo.python_version}</span>
              <span className="text-zinc-600">RAM</span>
              <span className="text-zinc-400">
                {systemInfo.ram_available_mb} / {systemInfo.ram_total_mb} MB
              </span>
              {systemInfo.cpu_temp_c != null && (
                <>
                  <span className="text-zinc-600">CPU Temp</span>
                  <span className={systemInfo.cpu_temp_c > 70 ? "text-orange-400" : "text-zinc-400"}>
                    {systemInfo.cpu_temp_c}°C
                  </span>
                </>
              )}
              <span className="text-zinc-600">Disk</span>
              <span className="text-zinc-400">
                {systemInfo.disk_free_mb} / {systemInfo.disk_total_mb} MB free
              </span>
            </div>
          )}

          <div className="flex gap-3 mt-3">
            <button onClick={handlePing} className="text-xs text-zinc-400 hover:text-white transition-colors">
              Ping
            </button>
            {(isOutdated || isUpdating) && (
              <button
                onClick={handleUpdate}
                disabled={isUpdating}
                className="text-xs text-orange-400 hover:text-orange-300 transition-colors disabled:opacity-50 inline-flex items-center gap-1"
              >
                {isUpdating && <span className="inline-block w-2.5 h-2.5 border border-orange-400 border-t-transparent rounded-full animate-spin" />}
                {isUpdating ? "Updating..." : "Update"}
              </button>
            )}
            <button
              onClick={() => {
                setForm({ ...device });
                setEditing(true);
              }}
              className="text-xs text-zinc-400 hover:text-white transition-colors"
            >
              Edit
            </button>
            <button onClick={() => {
              remove(device.id);
              notify("info", "Device deleted");
            }} className="text-xs text-red-400/60 hover:text-red-400 transition-colors">
              Delete
            </button>
          </div>

          {/* Update logs */}
          {updateLog && (
            <div className="mt-3">
              <button
                onClick={() => setShowLogs(!showLogs)}
                className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                {showLogs ? "Hide logs" : "Show logs"}
              </button>
              {showLogs && (
                <pre className="mt-1 p-2 rounded bg-zinc-950 border border-zinc-800/50 text-[10px] text-zinc-500 font-mono overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap">
                  {updateLog}
                </pre>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="space-y-2">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="Name"
          />
          <input
            value={form.ip_address}
            onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="IP Address"
          />
          <input
            value={form.osc_port}
            onChange={(e) => setForm({ ...form, osc_port: Number(e.target.value) })}
            type="number"
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="Port"
          />
          <div className="flex gap-2">
            <button onClick={handleSave} className="text-xs text-orange-400 hover:text-orange-300 transition-colors">
              Save
            </button>
            <button onClick={() => setEditing(false)} className="text-xs text-zinc-400 hover:text-white transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
