import { useEffect, useState } from "react";
import { useDeviceStore } from "../stores/device-store";
import type { DeviceType } from "../types/device";
import { downloadDeviceListExport } from "../api/devices";
import DeviceCard from "../components/device/DeviceCard";
import DeviceCardSkeleton from "../components/device/DeviceCardSkeleton";
import DeviceForm from "../components/device/DeviceForm";
import NetworkScanDialog from "../components/device/NetworkScanDialog";

type FilterKey = "all" | DeviceType;

export default function DevicesPage() {
  const list = useDeviceStore((s) => s.list);
  const loading = useDeviceStore((s) => s.loading);
  const fetchList = useDeviceStore((s) => s.fetchList);
  const latestVersion = useDeviceStore((s) => s.latestVersion);
  const fetchLatestVersion = useDeviceStore((s) => s.fetchLatestVersion);
  const deviceVersions = useDeviceStore((s) => s.deviceVersions);
  const deviceStatuses = useDeviceStore((s) => s.deviceStatuses);
  const updateAllOutdated = useDeviceStore((s) => s.updateAllOutdated);
  const updatingDevices = useDeviceStore((s) => s.updatingDevices);
  const [showForm, setShowForm] = useState(false);
  const [showScan, setShowScan] = useState(false);

  const [filterType, setFilterType] = useState<FilterKey>(() => {
    const v = localStorage.getItem("devices.filter");
    return v === "vents" || v === "trolley" ? v : "all";
  });
  const [compact, setCompact] = useState<boolean>(
    () => localStorage.getItem("devices.compact") === "1",
  );

  useEffect(() => {
    localStorage.setItem("devices.filter", filterType);
  }, [filterType]);
  useEffect(() => {
    localStorage.setItem("devices.compact", compact ? "1" : "0");
  }, [compact]);

  useEffect(() => {
    fetchList();
    fetchLatestVersion();
    const interval = setInterval(fetchLatestVersion, 60_000);
    return () => clearInterval(interval);
  }, [fetchList, fetchLatestVersion]);

  const counts = { vents: 0, trolley: 0 };
  list.forEach((d) => {
    counts[(d.type ?? "vents") as DeviceType]++;
  });
  const filtered =
    filterType === "all"
      ? list
      : list.filter((d) => (d.type ?? "vents") === filterType);

  const outdatedCount = latestVersion
    ? Object.entries(deviceVersions).filter(
        ([id, v]) => deviceStatuses[id] === "online" && v.version !== latestVersion.hash,
      ).length
    : 0;

  const isUpdatingAny = updatingDevices.size > 0;
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState<false | "csv" | "json">(false);

  async function handleExport(format: "csv" | "json") {
    setExporting(format);
    try {
      await downloadDeviceListExport(format);
    } catch (e) {
      console.error(e);
    } finally {
      setExporting(false);
    }
  }

  const adminHost =
    typeof window !== "undefined" ? window.location.hostname : "localhost";
  const sampleVents = list.find((d) => (d.type ?? "vents") === "vents");
  const sampleTrolley = list.find((d) => d.type === "trolley");

  async function handleRefresh() {
    setRefreshing(true);
    useDeviceStore.setState({ deviceVersions: {} });
    await fetchLatestVersion();
    await fetchList();
    setTimeout(() => setRefreshing(false), 1000);
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-10 pb-4 border-b border-white/10 gap-4">
        <div>
          <h2 className="text-3xl font-light tracking-tight text-white mb-1">Devices</h2>
          <p className="text-zinc-400 text-sm">Manage network devices and controllers</p>
          {latestVersion && latestVersion.hash !== "unknown" && (
            <p className="text-zinc-500 text-xs mt-1.5">
              Latest: <span className="font-mono text-zinc-400">{latestVersion.hash}</span>
              <span className="mx-1.5 text-zinc-600">·</span>
              <span className="text-zinc-500">{latestVersion.message}</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="inline-flex rounded-xl border border-white/10 bg-white/5 p-0.5">
            {(["all", "vents", "trolley"] as const).map((k) => {
              const isActive = filterType === k;
              const label =
                k === "all"
                  ? `All (${list.length})`
                  : k === "vents"
                  ? `Vents (${counts.vents})`
                  : `Trolley (${counts.trolley})`;
              return (
                <button
                  key={k}
                  onClick={() => setFilterType(k)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    isActive
                      ? "bg-orange-500/20 text-orange-300"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setCompact(!compact)}
            className="p-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-white transition-all duration-300"
            title={compact ? "Switch to grid view" : "Switch to compact list"}
          >
            {compact ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h6v6H4zM14 6h6v6h-6zM4 16h6v4H4zM14 16h6v4h-6z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-white transition-all duration-300 disabled:opacity-50"
            title="Refresh versions"
          >
            <svg className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          {outdatedCount > 0 && (
            <button
              onClick={updateAllOutdated}
              disabled={isUpdatingAny}
              className="px-5 py-2.5 bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 hover:border-orange-500/30 rounded-xl text-sm font-semibold text-orange-400 transition-all duration-300 shadow-sm hover:shadow-md disabled:opacity-50"
            >
              {isUpdatingAny ? "Updating..." : `Update All (${outdatedCount})`}
            </button>
          )}
          <button
            type="button"
            onClick={() => handleExport("csv")}
            disabled={!!exporting}
            className="px-5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-sm font-semibold text-white transition-all duration-300 shadow-sm hover:shadow-md disabled:opacity-50"
            title="Download device list as CSV"
          >
            {exporting === "csv" ? "Exporting…" : "Export CSV"}
          </button>
          <button
            type="button"
            onClick={() => handleExport("json")}
            disabled={!!exporting}
            className="px-5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-sm font-semibold text-zinc-300 transition-all duration-300 shadow-sm hover:shadow-md disabled:opacity-50"
            title="Download device list as JSON"
          >
            {exporting === "json" ? "Exporting…" : "Export JSON"}
          </button>
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

      <div className="mb-8 rounded-2xl border border-white/10 bg-zinc-900/40 backdrop-blur-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02]">
          <h3 className="text-sm font-medium text-zinc-200">OSC Bridge — targeting devices</h3>
          <p className="text-xs text-zinc-500 mt-1">
            From Max, TouchDesigner, or another machine, send OSC to this admin&apos;s{" "}
            <strong className="text-zinc-400 font-normal">bridge UDP port</strong> (default{" "}
            <code className="text-zinc-400">9002</code>, changeable in Settings). Prefix the real
            address with <code className="text-orange-300/90">/to/&lt;identifier&gt;/</code> where
            identifier is a device <strong className="text-zinc-400 font-normal">id</strong>,{" "}
            <strong className="text-zinc-400 font-normal">name</strong>,{" "}
            <strong className="text-zinc-400 font-normal">IP</strong>, or{" "}
            <strong className="text-zinc-400 font-normal">hardware_id</strong> from the export.
          </p>
        </div>
        <div className="px-5 py-4 space-y-3 text-[11px] leading-relaxed">
          <p className="text-zinc-500 uppercase tracking-wider font-semibold">Examples</p>
          <pre className="rounded-lg border border-white/10 bg-zinc-950/80 px-4 py-3 font-mono text-zinc-200 overflow-x-auto whitespace-pre-wrap">
            {sampleVents
              ? `# vents (fan 1 on device ${sampleVents.id})\noscsend ${adminHost} 9002 /to/${sampleVents.id}/vents/fan/1 f 0.5`
              : `# vents\noscsend ${adminHost} 9002 /to/<device-id>/vents/fan/1 f 0.5`}
          </pre>
          <pre className="rounded-lg border border-white/10 bg-zinc-950/80 px-4 py-3 font-mono text-zinc-200 overflow-x-auto whitespace-pre-wrap">
            {sampleTrolley
              ? `# trolley (position on ${sampleTrolley.id})\noscsend ${adminHost} 9002 /to/${sampleTrolley.id}/trolley/position f 0.42`
              : `# trolley\noscsend ${adminHost} 9002 /to/<device-id>/trolley/position f 0.42`}
          </pre>
        </div>
      </div>

      {showForm && (
        <div className="mb-8 p-6 rounded-2xl glass-panel animate-in fade-in slide-in-from-top-4 duration-500">
          <DeviceForm onCreated={() => setShowForm(false)} />
        </div>
      )}

      <div
        className={
          compact
            ? "grid grid-cols-1 gap-2"
            : "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
        }
      >
        {loading && list.length === 0
          ? Array.from({ length: 3 }).map((_, i) => (
              <div key={`skel-${i}`} className="animate-in fade-in duration-300" style={{ animationDelay: `${i * 60}ms` }}>
                <DeviceCardSkeleton />
              </div>
            ))
          : filtered.map((device, index) => (
              <div key={device.id} className="animate-in fade-in zoom-in-95 duration-500 fill-mode-both" style={{ animationDelay: `${index * 50}ms` }}>
                <DeviceCard device={device} compact={compact} />
              </div>
            ))}
      </div>

      {!loading && list.length > 0 && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center p-10 border border-white/5 border-dashed rounded-2xl bg-zinc-900/20 mt-6 text-zinc-500 text-sm">
          No {filterType} devices.
        </div>
      )}

      {!loading && !list.length && !showForm && (
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
