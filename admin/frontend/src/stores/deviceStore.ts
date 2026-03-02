import { defineStore } from "pinia";
import { ref } from "vue";
import type { Device, DiscoveredHost } from "../types/device";
import * as api from "../api/devices";

export const useDeviceStore = defineStore("devices", () => {
  const list = ref<Device[]>([]);
  const loading = ref(false);

  const scanning = ref(false);
  const scanResults = ref<DiscoveredHost[]>([]);
  const scanError = ref<string | null>(null);

  async function fetchList() {
    loading.value = true;
    try {
      list.value = await api.listDevices();
    } finally {
      loading.value = false;
    }
  }

  async function create(data: Partial<Device>) {
    const dev = await api.createDevice(data);
    await fetchList();
    return dev;
  }

  async function update(device: Device) {
    await api.updateDevice(device.id, device);
    await fetchList();
  }

  async function remove(id: string) {
    await api.deleteDevice(id);
    await fetchList();
  }

  async function ping(id: string) {
    return api.pingDevice(id);
  }

  function scan(subnet?: string) {
    scanning.value = true;
    scanError.value = null;
    scanResults.value = [];

    api.scanNetworkStream(
      (host) => {
        // Update existing entry if SSH info arrives, otherwise add new
        const idx = scanResults.value.findIndex((h) => h.ip === host.ip);
        if (idx >= 0) {
          scanResults.value[idx] = host;
        } else {
          scanResults.value.push(host);
        }
      },
      () => {
        scanning.value = false;
      },
      subnet,
    );
  }

  function clearScanResults() {
    scanResults.value = [];
    scanError.value = null;
  }

  async function addDiscovered(hosts: { ip: string; osc_port: number; name: string }[]) {
    for (const h of hosts) {
      await api.createDevice({ name: h.name, ip_address: h.ip, osc_port: h.osc_port });
    }
    await fetchList();
  }

  return {
    list, loading,
    scanning, scanResults, scanError,
    fetchList, create, update, remove, ping,
    scan, clearScanResults, addDiscovered,
  };
});
