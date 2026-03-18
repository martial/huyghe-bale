import { create } from "zustand";
import type { Device, DiscoveredHost } from "../types/device";
import * as api from "../api/devices";

interface DeviceState {
  list: Device[];
  deviceStatuses: Record<string, boolean>;
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
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  list: [],
  deviceStatuses: {},
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
}));

// Initialize status stream automatically
api.monitorDeviceStatus((statuses) => {
  useDeviceStore.setState({ deviceStatuses: statuses });
});
