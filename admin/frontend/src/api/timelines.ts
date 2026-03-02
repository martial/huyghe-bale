import { get, post, put, del } from "./client";
import type { Timeline, TimelineSummary } from "../types/timeline";

export function listTimelines() {
  return get<TimelineSummary[]>("/timelines");
}

export function getTimeline(id: string) {
  return get<Timeline>(`/timelines/${id}`);
}

export function createTimeline(data: Partial<Timeline>) {
  return post<Timeline>("/timelines", data);
}

export function updateTimeline(id: string, data: Timeline) {
  return put<Timeline>(`/timelines/${id}`, data);
}

export function deleteTimeline(id: string) {
  return del(`/timelines/${id}`);
}

export function duplicateTimeline(id: string) {
  return post<Timeline>(`/timelines/${id}/duplicate`);
}
