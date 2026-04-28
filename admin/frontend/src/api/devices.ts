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

/** Download registered devices from GET /devices/export (CSV default, JSON optional). */
export async function downloadDeviceListExport(format: "csv" | "json" = "csv"): Promise<void> {
  const qs = format === "json" ? "?format=json" : "";
  const res = await fetch(`/api/v1/devices/export${qs}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err?.error === "string" ? err.error : `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition");
  let filename = format === "json" ? "devices.json" : "devices.csv";
  const m = cd?.match(/filename="([^"]+)"/);
  if (m?.[1]) filename = m[1];
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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

export async function sendTestValue(
  deviceIds: string[],
  valueA: number,
  valueB: number,
  method: "osc" | "http",
) {
  console.log(`[Test] Sending ${method} a=${valueA} b=${valueB} to devices:`, deviceIds);
  return post<{ ok: boolean; results: Record<string, unknown> }>("/devices/test-send", {
    device_ids: deviceIds,
    value_a: valueA,
    value_b: valueB,
    method,
  });
}

/** Live alarm payload for one device — emitted as part of the device-status SSE.
 * Backend only sets a key when there's at least one active channel; missing key
 * means the device is healthy. */
export interface DeviceAlarms {
  /** Channels in alarm. 0/1 = fan 1 tach A/B, 2/3 = fan 2 tach A/B. */
  active: number[];
  /** Threshold (RPM) under which channels are considered to be in alarm. */
  threshold: number;
}

export function monitorDeviceStatus(
  onStatusUpdate: (
    statuses: Record<string, DeviceStatus>,
    versions: Record<string, DeviceVersion>,
    systemInfo: Record<string, DeviceSystemInfo>,
    lastSeen: Record<string, number>,
    alarms: Record<string, DeviceAlarms>,
  ) => void,
) {
  const eventSource = new EventSource("/api/v1/devices/status");

  eventSource.onopen = () => {
    console.log("[HeartbeatSSE] Connected to /api/v1/devices/status");
  };

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.statuses) {
        onStatusUpdate(
          data.statuses,
          data.versions || {},
          data.system_info || {},
          data.last_seen || {},
          data.alarms || {},
        );
      } else {
        onStatusUpdate(data as Record<string, DeviceStatus>, {}, {}, {}, {});
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
