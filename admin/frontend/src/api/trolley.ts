import { get, post, put, del } from "./client";
import type {
  TrolleyTimeline,
  TrolleyTimelineSummary,
  TrolleyCommand,
  TrolleyStatus,
} from "../types/trolley";

// ── timelines ──────────────────────────────────────────────────────────────

export function listTrolleyTimelines() {
  return get<TrolleyTimelineSummary[]>("/trolley-timelines");
}

export function getTrolleyTimeline(id: string) {
  return get<TrolleyTimeline>(`/trolley-timelines/${id}`);
}

export function createTrolleyTimeline(data: Partial<TrolleyTimeline>) {
  return post<TrolleyTimeline>("/trolley-timelines", data);
}

export function updateTrolleyTimeline(id: string, data: TrolleyTimeline) {
  return put<TrolleyTimeline>(`/trolley-timelines/${id}`, data);
}

export function deleteTrolleyTimeline(id: string) {
  return del(`/trolley-timelines/${id}`);
}

export function duplicateTrolleyTimeline(id: string) {
  return post<TrolleyTimeline>(`/trolley-timelines/${id}/duplicate`);
}

// ── raw control ────────────────────────────────────────────────────────────

export function sendTrolleyCommand(
  deviceId: string,
  command: TrolleyCommand,
  value?: number | string,
) {
  return post<{ ok: boolean; sent?: { address: string; value: unknown } }>(
    `/trolley-control/${deviceId}/command`,
    { command, value: value ?? 0 },
  );
}

/** Settings live in a single 'config_set' command that takes (key, value).
 *  Use this for typed setting writes; pair with sendTrolleyCommand("config_save")
 *  once all desired keys are staged on the Pi. */
export function setTrolleyConfig(
  deviceId: string,
  key: string,
  value: number | string | boolean,
) {
  return post<{ ok: boolean }>(
    `/trolley-control/${deviceId}/command`,
    { command: "config_set", key, value },
  );
}

export function fetchTrolleyStatus(deviceId: string) {
  return get<TrolleyStatus>(`/trolley-control/${deviceId}/status`);
}
