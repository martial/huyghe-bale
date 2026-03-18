import { useState } from "react";
import type { Device } from "../../types/device";
import { useDeviceStore } from "../../stores/device-store";
import { useNotificationStore } from "../../stores/notification-store";

export default function DeviceCard({ device }: { device: Device }) {
  const update = useDeviceStore((s) => s.update);
  const remove = useDeviceStore((s) => s.remove);
  const ping = useDeviceStore((s) => s.ping);
  const notify = useNotificationStore((s) => s.notify);
  const isOnline = useDeviceStore((s) => s.deviceStatuses[device.id]);

  const [pingStatus, setPingStatus] = useState<"idle" | "pinging" | "ok" | "error">("idle");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ ...device });

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

  async function handleSave() {
    await update(form as Device);
    notify("success", "Device updated successfully");
    setEditing(false);
  }

  return (
    <div className="p-5 rounded-xl border border-zinc-800/50 bg-zinc-900/80 shadow-sm transition-all duration-200 hover:border-zinc-700/50 hover:scale-[1.02]">
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
          <div className="flex gap-3 mt-3">
            <button onClick={handlePing} className="text-xs text-zinc-400 hover:text-white transition-colors">
              Ping
            </button>
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
