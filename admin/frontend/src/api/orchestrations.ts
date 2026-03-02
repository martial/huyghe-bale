import { get, post, put, del } from "./client";
import type { Orchestration } from "../types/orchestration";

export function listOrchestrations() {
  return get<Orchestration[]>("/orchestrations");
}

export function getOrchestration(id: string) {
  return get<Orchestration>(`/orchestrations/${id}`);
}

export function createOrchestration(data: Partial<Orchestration>) {
  return post<Orchestration>("/orchestrations", data);
}

export function updateOrchestration(id: string, data: Orchestration) {
  return put<Orchestration>(`/orchestrations/${id}`, data);
}

export function deleteOrchestration(id: string) {
  return del(`/orchestrations/${id}`);
}
