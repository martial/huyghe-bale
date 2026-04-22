import { get, post } from "./client";
import type { VentsCommand, VentsStatus, VentsMode } from "../types/vents";

export interface VentsCommandBody {
  command: VentsCommand;
  index?: number;
  value: number | string | boolean;
}

export function sendVentsCommand(
  deviceId: string,
  body: VentsCommandBody,
) {
  return post<{ ok: boolean; sent?: { address: string; value: number | string } }>(
    `/vents-control/${deviceId}/command`,
    body,
  );
}

export function setVentsPeltier(deviceId: string, index: 1 | 2 | 3, on: boolean) {
  return sendVentsCommand(deviceId, { command: "peltier", index, value: on ? 1 : 0 });
}

export function setVentsFan(deviceId: string, index: 1 | 2, value_0_1: number) {
  return sendVentsCommand(deviceId, { command: "fan", index, value: value_0_1 });
}

export function setVentsMode(deviceId: string, mode: VentsMode) {
  return sendVentsCommand(deviceId, { command: "mode", value: mode });
}

export function setVentsTarget(deviceId: string, celsius: number) {
  return sendVentsCommand(deviceId, { command: "target", value: celsius });
}

export function fetchVentsStatus(deviceId: string) {
  return get<VentsStatus>(`/vents-control/${deviceId}/status`);
}
