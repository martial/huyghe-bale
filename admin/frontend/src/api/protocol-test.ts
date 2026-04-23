import type { Device } from "../types/device";

export interface ProtocolTestOscPayload {
  device_id: string;
  address: string;
  values?: (number | string | boolean)[];
}

export interface ProtocolTestHttpPayload {
  device_id: string;
  method: "GET" | "POST";
  path: string;
  json?: Record<string, unknown>;
}

export interface ProtocolTestBridgePayload {
  address?: string;
  inner_address?: string;
  device_id?: string;
  values?: (number | string | boolean)[];
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/v1/protocol-test${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data?.error === "string" ? data.error : `Request failed (${res.status})`);
  }
  return data as T;
}

export function protocolTestOsc(body: ProtocolTestOscPayload) {
  return post<{ ok: boolean; sent?: { address: string; values: unknown[] } }>("/osc", body);
}

export function protocolTestHttp(body: ProtocolTestHttpPayload) {
  return post<{ ok: boolean; body?: unknown; error?: string }>("/http", body);
}

export function protocolTestBridge(body: ProtocolTestBridgePayload) {
  return post<{ ok: boolean; sent?: { address: string; values: unknown[] } }>("/bridge", body);
}

/** Which devices appear in the quick-test dropdown for an OSC address. */
export function filterDevicesForOscAddress(devices: Device[], address: string): Device[] {
  if (address.startsWith("/sys/")) return devices.filter((d) => d.ip_address);
  if (address.startsWith("/vents/")) return devices.filter((d) => (d.type ?? "vents") === "vents" && d.ip_address);
  if (address.startsWith("/trolley/")) return devices.filter((d) => d.type === "trolley" && d.ip_address);
  return [];
}
