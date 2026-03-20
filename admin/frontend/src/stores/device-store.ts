import { create } from "zustand";
import type { Device, DeviceStatus, DeviceVersion, DeviceSystemInfo, LatestVersion, DiscoveredHost } from "../types/device";
import * as api from "../api/devices";

interface DeviceState {
  list: Device[];
  deviceStatuses: Record<string, DeviceStatus>;
  deviceVersions: Record<string, DeviceVersion>;
  deviceSystemInfo: Record<string, DeviceSystemInfo>;
  latestVersion: LatestVersion | null;
  updatingDevices: Set<string>;
  restartingDevices: Set<string>;
  updateLogs: Record<string, string>;
  loading: boolean;
  scanning: boolean;
  scanResults: DiscoveredHost[];
  scanError: string | null;
  fetchList: () => Promise<void>;
  createDevice: (data: Partial<Device>) => Promise<Device>;
  update: (device: Device) => Promise<void>;
  remove: (id: string) => Promise<void>;
  ping: (id: string) => Promise<{ ok: boolean; message: string }>;
  scan: (subnet?: string) => void;
  clearScanResults: () => void;
  addDiscovered: (hosts: { ip: string; osc_port: number; name: string }[]) => Promise<void>;
  fetchLatestVersion: () => Promise<void>;
  updateSoftware: (id: string) => Promise<void>;
  updateAllOutdated: () => Promise<void>;
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  list: [],
  deviceStatuses: {},
  deviceVersions: {},
  deviceSystemInfo: {},
  latestVersion: null,
  updatingDevices: new Set(),
  restartingDevices: new Set(),
  updateLogs: {},
  loading: false,
  scanning: false,
  scanResults: [],
  scanError: null,

  async fetchList() {
    set({ loading: true });
    try {
      const list = await api.listDevices();
      set({ list });
    } finally {
      set({ loading: false });
    }
  },

  async createDevice(data: Partial<Device>) {
    const dev = await api.createDevice(data);
    await get().fetchList();
    return dev;
  },

  async update(device: Device) {
    await api.updateDevice(device.id, device);
    await get().fetchList();
  },

  async remove(id: string) {
    await api.deleteDevice(id);
    await get().fetchList();
  },

  async ping(id: string) {
    return api.pingDevice(id);
  },

  scan(subnet?: string) {
    set({ scanning: true, scanError: null, scanResults: [] });
    api.scanNetworkStream(
      (host) => {
        const results = [...get().scanResults];
        const idx = results.findIndex((h) => h.ip === host.ip);
        if (idx >= 0) {
          results[idx] = host;
        } else {
          results.push(host);
        }
        set({ scanResults: results });
      },
      () => {
        set({ scanning: false });
      },
      subnet,
    );
  },

  clearScanResults() {
    set({ scanResults: [], scanError: null });
  },

  async addDiscovered(hosts) {
    for (const h of hosts) {
      await api.createDevice({ name: h.name, ip_address: h.ip, osc_port: h.osc_port });
    }
    await get().fetchList();
  },

  async fetchLatestVersion() {
    try {
      const latest = await api.getLatestVersion();
      set({ latestVersion: latest });
    } catch (e) {
      console.error("Failed to fetch latest version:", e);
    }
  },

  async updateSoftware(id: string) {
    const updating = new Set(get().updatingDevices);
    updating.add(id);
    set({ updatingDevices: updating });
    try {
      const result = await api.updateDeviceSoftware(id);
      const logs = { ...get().updateLogs, [id]: result.logs };
      // Update cached version if successful
      if (result.success && result.new_version) {
        const versions = { ...get().deviceVersions };
        versions[id] = { version: result.new_version, version_date: "" };
        set({ updateLogs: logs, deviceVersions: versions });
      } else {
        set({ updateLogs: logs });
      }
    } catch (e) {
      const logs = { ...get().updateLogs, [id]: String(e) };
      set({ updateLogs: logs });
    } finally {
      const afterUpdating = new Set(get().updatingDevices);
      afterUpdating.delete(id);
      // Mark device as restarting, clear its cached version
      const restarting = new Set(get().restartingDevices);
      restarting.add(id);
      const versions = { ...get().deviceVersions };
      delete versions[id];
      set({ updatingDevices: afterUpdating, restartingDevices: restarting, deviceVersions: versions });
      // Fetch fresh latest version from backend
      await get().fetchLatestVersion();
    }
  },

  async updateAllOutdated() {
    const { deviceVersions, latestVersion, deviceStatuses } = get();
    if (!latestVersion) return;
    const outdated = Object.entries(deviceVersions)
      .filter(([id, v]) => deviceStatuses[id] === "online" && v.version !== latestVersion.hash)
      .map(([id]) => id);
    await Promise.all(outdated.map((id) => get().updateSoftware(id)));
  },
}));

// Initialize status stream automatically
let cleanupStatusStream: (() => void) | null = null;

function startStatusStream() {
  cleanupStatusStream?.();
  cleanupStatusStream = api.monitorDeviceStatus((statuses, versions, systemInfo) => {
    const state = useDeviceStore.getState();
    const prevStatuses = state.deviceStatuses;
    const prevVersions = state.deviceVersions;

    let statusChanged = false;
    for (const id in statuses) {
      if (prevStatuses[id] !== statuses[id]) { statusChanged = true; break; }
    }
    if (!statusChanged) {
      for (const id in prevStatuses) {
        if (!(id in statuses)) { statusChanged = true; break; }
      }
    }

    const versionChanged = JSON.stringify(versions) !== JSON.stringify(prevVersions);
    const sysInfoChanged = JSON.stringify(systemInfo) !== JSON.stringify(state.deviceSystemInfo);

    // Clear restarting flag once we get a fresh version for that device
    const restarting = state.restartingDevices;
    if (restarting.size > 0) {
      const newRestarting = new Set(restarting);
      for (const id of restarting) {
        if (versions[id]) {
          newRestarting.delete(id);
        }
      }
      if (newRestarting.size !== restarting.size) {
        useDeviceStore.setState({ restartingDevices: newRestarting });
      }
    }

    if (statusChanged || versionChanged || sysInfoChanged) {
      const update: Record<string, unknown> = {};
      if (statusChanged) update.deviceStatuses = statuses;
      if (versionChanged) update.deviceVersions = versions;
      if (sysInfoChanged) update.deviceSystemInfo = systemInfo;
      useDeviceStore.setState(update);
    }
  });
}

startStatusStream();
useDeviceStore.getState().fetchList();

if (import.meta.hot) {
  import.meta.hot.dispose(() => cleanupStatusStream?.());
}
