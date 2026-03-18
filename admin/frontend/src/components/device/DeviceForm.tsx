import { useState } from "react";
import { useDeviceStore } from "../../stores/device-store";
import { useNotificationStore } from "../../stores/notification-store";

export default function DeviceForm({ onCreated }: { onCreated: () => void }) {
  const createDevice = useDeviceStore((s) => s.createDevice);
  const notify = useNotificationStore((s) => s.notify);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [port, setPort] = useState(9000);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createDevice({ name, ip_address: ip, osc_port: port });
    notify("success", "Device added successfully");
    setName("");
    setIp("");
    setPort(9000);
    onCreated();
  }

  return (
    <form onSubmit={handleSubmit} className="p-5 rounded-xl border border-zinc-700/50 bg-zinc-900/80 space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-zinc-400 block mb-1">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
            placeholder="Room 11"
          />
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
