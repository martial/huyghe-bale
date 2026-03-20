import { get, post, put, del } from "./client";
import type { Device, DeviceStatus, DeviceVersion, DeviceSystemInfo, LatestVersion, UpdateResult, DiscoveredHost } from "../types/device";

export function listDevices() {
  return get<Device[]>("/devices");
}

export function getDevice(id: string) {
  return get<Device>(`/devices/${id}`);
}

export function createDevice(data: Partial<Device>) {
  return post<Device>("/devices", data);
}

export function updateDevice(id: string, data: Device) {
  return put<Device>(`/devices/${id}`, data);
}

export function deleteDevice(id: string) {
  return del(`/devices/${id}`);
}

export function pingDevice(id: string) {
  return post<{ ok: boolean; message: string }>(`/devices/${id}/ping`);
}

export function getLatestVersion() {
  return get<LatestVersion>("/devices/version/latest");
}

export function updateDeviceSoftware(id: string) {
  return post<UpdateResult>(`/devices/${id}/update`);
}

export function scanNetworkStream(
  onHost: (host: DiscoveredHost) => void,
  onDone: () => void,
  subnet?: string,
) {
  const controller = new AbortController();

  fetch("/api/v1/devices/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subnet ? { subnet } : {}),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onDone();
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6);
          try {
            const event = JSON.parse(json);
            if (event.type === "host") {
              onHost(event as DiscoveredHost);
            } else if (event.type === "done" || event.type === "error") {
              onDone();
              return;
            }
          } catch {
            // skip malformed lines
          }
        }
      }
      onDone();
    })
    .catch(() => {
      onDone();
    });

  return controller;
}

export function monitorDeviceStatus(
  onStatusUpdate: (
    statuses: Record<string, DeviceStatus>,
    versions: Record<string, DeviceVersion>,
    systemInfo: Record<string, DeviceSystemInfo>,
  ) => void,
) {
  const eventSource = new EventSource("/api/v1/devices/status");

  eventSource.onopen = () => {
    console.log("[HeartbeatSSE] Connected to /api/v1/devices/status");
  };

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      // New shape: {statuses, versions, system_info} — fallback for old flat shape
      if (data.statuses) {
        onStatusUpdate(data.statuses, data.versions || {}, data.system_info || {});
      } else {
        onStatusUpdate(data as Record<string, DeviceStatus>, {}, {});
      }
    } catch (e) {
      console.error("[HeartbeatSSE] Parse error:", e);
    }
  };

  eventSource.onerror = (e) => {
    console.error("[HeartbeatSSE] Connection error:", e);
  };

  return () => {
    eventSource.close();
  };
}
