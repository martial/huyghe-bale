import { useEffect, useState } from "react";
import { useDeviceStore } from "../stores/device-store";
import DeviceCard from "../components/device/DeviceCard";
import DeviceForm from "../components/device/DeviceForm";
import NetworkScanDialog from "../components/device/NetworkScanDialog";

export default function DevicesPage() {
  const list = useDeviceStore((s) => s.list);
  const fetchList = useDeviceStore((s) => s.fetchList);
  const [showForm, setShowForm] = useState(false);
  const [showScan, setShowScan] = useState(false);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  return (
    <div className="p-10 max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-10 pb-4 border-b border-white/10 gap-4">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Devices</h2>
          <p className="text-zinc-400 text-sm">Manage network devices and controllers</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowScan(true)}
            className="px-5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-sm font-semibold text-white transition-all duration-300 shadow-sm hover:shadow-md"
          >
            Scan Network
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-5 py-2.5 bg-gradient-to-r from-orange-500 to-orange-400 hover:from-orange-400 hover:to-orange-300 rounded-xl text-sm font-semibold text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:shadow-[0_0_30px_rgba(249,115,22,0.5)] transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-95"
          >
            {showForm ? "Cancel" : "Add Device"}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="mb-8 p-6 rounded-2xl glass-panel animate-in fade-in slide-in-from-top-4 duration-500">
          <DeviceForm onCreated={() => setShowForm(false)} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {list.map((device, index) => (
          <div key={device.id} className="animate-in fade-in zoom-in-95 duration-500 fill-mode-both" style={{ animationDelay: `${index * 50}ms` }}>
            <DeviceCard device={device} />
          </div>
        ))}
      </div>

      {!list.length && !showForm && (
        <div className="flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20 mt-8">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-5 border border-white/10 shadow-inner">
            <svg className="w-8 h-8 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
          </div>
          <p className="text-zinc-300 text-lg font-medium">No devices connected</p>
          <p className="text-zinc-500 text-sm mt-2">Scan your network or add a device manually.</p>
        </div>
      )}

      {showScan && <NetworkScanDialog onClose={() => setShowScan(false)} />}
    </div>
  );
}
