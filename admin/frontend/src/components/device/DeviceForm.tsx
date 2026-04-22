import { useState } from "react";
import { useDeviceStore } from "../../stores/device-store";
import { useNotificationStore } from "../../stores/notification-store";
import { DEVICE_TYPES, type DeviceType } from "../../types/device";

export default function DeviceForm({ onCreated }: { onCreated: () => void }) {
  const createDevice = useDeviceStore((s) => s.createDevice);
  const notify = useNotificationStore((s) => s.notify);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [port, setPort] = useState(9000);
  const [type, setType] = useState<DeviceType>("vents");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createDevice({ name, ip_address: ip, osc_port: port, type });
    notify("success", "Device added successfully");
    setName("");
    setIp("");
    setPort(9000);
    setType("vents");
    onCreated();
  }

  return (
    <form onSubmit={handleSubmit} className="p-5 rounded-xl border border-zinc-700/50 bg-zinc-900/80 space-y-3">
      <div className="grid grid-cols-4 gap-3">
        <div>
          <label className="text-xs text-zinc-400 block mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="Room 11"
          />
          <p className="text-[10px] text-zinc-500 mt-1">
            Used in OSC <span className="font-mono">/to/&lt;name&gt;/…</span> · no slashes
          </p>
        </div>
        <div>
          <label className="text-xs text-zinc-400 block mb-1">IP Address</label>
          <input
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            required
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="192.168.1.101"
          />
        </div>
        <div>
          <label className="text-xs text-zinc-400 block mb-1">OSC Port</label>
          <input
            value={port}
            onChange={(e) => setPort(Number(e.target.value))}
            type="number"
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
          />
        </div>
        <div>
          <label className="text-xs text-zinc-400 block mb-1">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as DeviceType)}
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
          >
            {DEVICE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>
      <button
        type="submit"
        className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded-lg text-sm font-medium transition-all duration-200"
      >
        Add Device
      </button>
    </form>
  );
}
