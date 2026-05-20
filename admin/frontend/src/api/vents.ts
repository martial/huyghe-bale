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

/** Toggle the per-device "unique peltier" sub-mode of auto. When true, the
 *  Pi drives one cell at a time, with a per-cell minimum-OFF cooldown using
 *  the global `peltier_rest_s` threshold. */
export function setVentsUniquePeltier(deviceId: string, enabled: boolean) {
  return sendVentsCommand(deviceId, { command: "unique_peltier", value: enabled ? 1 : 0 });
}

/** Set the shared minimum-OFF threshold (seconds) used by unique-peltier
 *  auto mode. Range 0–3600. Per-cell timers tick independently against this
 *  value. Normally pushed from the Settings page; this helper lets the
 *  device panel override on a single device. */
export function setVentsPeltierRestSeconds(deviceId: string, seconds: number) {
  return sendVentsCommand(deviceId, { command: "peltier_rest_s", value: seconds });
}

export function fetchVentsStatus(deviceId: string) {
  return get<VentsStatus>(`/vents-control/${deviceId}/status`);
}
