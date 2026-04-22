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
  value?: number,
) {
  return post<{ ok: boolean; sent?: { address: string; value: number } }>(
    `/trolley-control/${deviceId}/command`,
    { command, value: value ?? 0 },
  );
}

export function fetchTrolleyStatus(deviceId: string) {
  return get<TrolleyStatus>(`/trolley-control/${deviceId}/status`);
}
