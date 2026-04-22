import { useState } from "react";
import type { Device, DeviceType } from "../../types/device";
import { DEVICE_TYPES } from "../../types/device";
import { useDeviceStore } from "../../stores/device-store";
import { useNotificationStore } from "../../stores/notification-store";
import { useVentsStatus } from "../../hooks/use-vents-status";
import { useTrolleyStatus } from "../../hooks/use-trolley-status";
import VentsHero from "./VentsHero";
import TrolleyHero from "./TrolleyHero";
import VentsTestPanel from "./VentsTestPanel";

const TYPE_BADGE: Record<DeviceType, string> = {
  vents: "bg-orange-500/10 text-orange-300 border-orange-500/30",
  trolley: "bg-sky-500/10 text-sky-300 border-sky-500/30",
};

// Small chevron that rotates when the details section is expanded.
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8.25 4.5l7.5 7.5-7.5 7.5" />
    </svg>
  );
}

/** Hero block dispatches on device type.
 *  Hooks are called at the top level of each variant — the render branch
 *  is stable per-device for its lifetime (type doesn't change at runtime),
 *  so this doesn't break rules-of-hooks. */
function VentsHeroSlot({ device }: { device: Device }) {
  const { status, stale, lastPushAgeS } = useVentsStatus(device.id);
  return (
    <>
      <VentsHero status={status} stale={stale} lastPushAgeS={lastPushAgeS} />
      <DeviceCardDetails device={device}>
        <VentsTestPanel device={device} status={status} />
      </DeviceCardDetails>
    </>
  );
}

function TrolleyHeroSlot({ device }: { device: Device }) {
  const { status, stale, lastPushAgeS } = useTrolleyStatus(device.id);
  return (
    <>
      <TrolleyHero status={status} stale={stale} lastPushAgeS={lastPushAgeS} />
      <DeviceCardDetails device={device} />
    </>
  );
}

/** Collapsible details section. Contains the full system-info grid and,
 *  for vents, the raw-control panel (children). For trolley it's just
 *  system info — full controls live on /trolleys. */
function DeviceCardDetails({
  device,
  children,
}: {
  device: Device;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const systemInfo = useDeviceStore((s) => s.deviceSystemInfo[device.id]);
  const isOnline = useDeviceStore((s) => s.deviceStatuses[device.id] === "online");

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Chevron open={open} />
        {open ? "Hide details" : "Details"}
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {/* Controls (vents only) */}
          {children && (
            <div className="p-3 rounded-xl border border-white/5 bg-black/20">
              {children}
            </div>
          )}

          {/* System info */}
          {isOnline && systemInfo && (
            <div className="p-3 rounded-xl border border-white/5 bg-black/20 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono text-zinc-500">
              <span className="text-zinc-600">Model</span>
              <span className="text-zinc-400 truncate">{systemInfo.model}</span>
              <span className="text-zinc-600">OS</span>
              <span className="text-zinc-400 truncate">{systemInfo.os}</span>
              {systemInfo.ip && (
                <>
                  <span className="text-zinc-600">IP</span>
                  <span className="text-zinc-400 font-mono">{systemInfo.ip}</span>
                </>
              )}
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
        </div>
      )}
    </div>
  );
}

export default function DeviceCard({ device }: { device: Device }) {
  const update = useDeviceStore((s) => s.update);
  const remove = useDeviceStore((s) => s.remove);
  const updateSoftware = useDeviceStore((s) => s.updateSoftware);
  const notify = useNotificationStore((s) => s.notify);
  const isOnline = useDeviceStore((s) => s.deviceStatuses[device.id] === "online");
  const deviceVersion = useDeviceStore((s) => s.deviceVersions[device.id]);
  const latestVersion = useDeviceStore((s) => s.latestVersion);
  const isUpdating = useDeviceStore((s) => s.updatingDevices.has(device.id));
  const isRestarting = useDeviceStore((s) => s.restartingDevices.has(device.id));
  const updateLog = useDeviceStore((s) => s.updateLogs[device.id]);
  const effectiveType: DeviceType = device.type || "vents";

  const isOutdated =
    isOnline && deviceVersion && latestVersion && deviceVersion.version !== latestVersion.hash;

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ ...device });
  const [showLogs, setShowLogs] = useState(false);

  async function handleUpdate() {
    await updateSoftware(device.id);
    setShowLogs(true);
  }

  async function handleSave() {
    await update(form as Device);
    notify("success", "Device updated successfully");
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="p-5 rounded-2xl border border-zinc-800/50 bg-zinc-900/80">
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
          <label className="text-xs text-zinc-500 block">
            Type
            <select
              value={form.type || "vents"}
              onChange={(e) => setForm({ ...form, type: e.target.value as DeviceType })}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-orange-500/50 transition-colors"
            >
              {DEVICE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <button onClick={handleSave} className="text-xs text-orange-400 hover:text-orange-300 transition-colors">
              Save
            </button>
            <button onClick={() => setEditing(false)} className="text-xs text-zinc-400 hover:text-white transition-colors">
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 rounded-2xl border border-zinc-800/50 bg-zinc-900/80 shadow-sm transition-all duration-200 hover:border-zinc-700/40">
      {/* Compact header: status + name + meta */}
      <div className="flex items-start gap-3">
        <span
          className={`mt-1.5 inline-flex w-2.5 h-2.5 rounded-full transition-colors flex-shrink-0 ${
            isOnline
              ? "bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]"
              : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"
          }`}
          title={isOnline ? "online" : "offline"}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className={`font-medium text-lg leading-tight ${device.needs_repair ? "text-zinc-500 italic" : "text-zinc-100"}`}>
              {device.name || "(unnamed device)"}
            </p>
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${TYPE_BADGE[effectiveType]}`}>
              {effectiveType}
            </span>
            {device.needs_repair && (
              <span
                className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-yellow-500/10 text-yellow-300 border-yellow-500/30"
                title={`Missing: ${(device.missing_fields || []).join(", ")}`}
              >
                needs repair
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-x-3 gap-y-0.5 flex-wrap text-[11px] text-zinc-500 font-mono">
            <span>{device.ip_address || "—"}:{device.osc_port}</span>
            {device.hardware_id && <span className="text-zinc-600">{device.hardware_id}</span>}

            {/* Version state: show restarting spinner, version hash, or update pill */}
            {(isRestarting || (isOnline && !deviceVersion)) && (
              <span className="inline-flex items-center gap-1 text-zinc-500">
                <span className="inline-block w-2 h-2 border border-zinc-500 border-t-transparent rounded-full animate-spin" />
                {isRestarting ? "restarting" : "fetching version"}
              </span>
            )}
            {!isRestarting && isOnline && deviceVersion && (
              <>
                <span className="text-zinc-400">{deviceVersion.version}</span>
                {isOutdated ? (
                  <span className="text-orange-400">update available</span>
                ) : latestVersion && (
                  <span className="text-emerald-400/70">up to date</span>
                )}
              </>
            )}
          </div>
          {device.needs_repair && (
            <p className="text-[10px] text-yellow-400/80 mt-1">
              Click Edit and fill in {(device.missing_fields || []).join(", ")} to restore this device.
            </p>
          )}
        </div>
      </div>

      {/* Hero: controller-specific big stat */}
      {!device.needs_repair && isOnline && (
        <div className="mt-4">
          {effectiveType === "vents" && <VentsHeroSlot device={device} />}
          {effectiveType === "trolley" && <TrolleyHeroSlot device={device} />}
        </div>
      )}

      {/* Offline placeholder — scanning for device status */}
      {!device.needs_repair && !isOnline && (
        <div className="mt-4 rounded-2xl border border-white/5 bg-zinc-950/40 px-5 py-6 text-center text-xs text-zinc-500">
          Device offline — no live status available.
        </div>
      )}

      {/* Footer actions */}
      <div className="flex gap-4 mt-4 pt-3 border-t border-zinc-800/50">
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
        <button
          onClick={() => {
            remove(device.id);
            notify("info", "Device deleted");
          }}
          className="text-xs text-red-400/60 hover:text-red-400 transition-colors"
        >
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
    </div>
  );
}
