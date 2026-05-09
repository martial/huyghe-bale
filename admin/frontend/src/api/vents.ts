import { get, post } from "./client";
import type {
  VentsActiveTarget,
  VentsCommand,
  VentsMode,
  VentsStatus,
} from "../types/vents";

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

/** Back-compat alias — sets the hot setpoint via the legacy `/vents/target`
 *  address. New code should prefer setVentsHotTarget. */
export function setVentsTarget(deviceId: string, celsius: number) {
  return sendVentsCommand(deviceId, { command: "target", value: celsius });
}

export function setVentsHotTarget(deviceId: string, celsius: number) {
  return sendVentsCommand(deviceId, { command: "target_hot", value: celsius });
}

export function setVentsColdTarget(deviceId: string, celsius: number) {
  return sendVentsCommand(deviceId, { command: "target_cold", value: celsius });
}

/** Flip which side currently regulates without writing a new value to either
 *  setpoint. Used to re-activate a greyed-out slider with one click. */
export function setVentsActiveTarget(
  deviceId: string,
  side: VentsActiveTarget,
) {
  return sendVentsCommand(deviceId, { command: "target_active", value: side });
}

export function assignVentsProbe(
  deviceId: string,
  role: "hot" | "cold",
  romId: string,
) {
  return sendVentsCommand(deviceId, {
    command: role === "hot" ? "probe_assign_hot" : "probe_assign_cold",
    value: romId,
  });
}

export function clearVentsProbe(deviceId: string, role: "hot" | "cold" | "both") {
  return sendVentsCommand(deviceId, { command: "probe_clear", value: role });
}

export function fetchVentsStatus(deviceId: string) {
  return get<VentsStatus>(`/vents-control/${deviceId}/status`);
}
