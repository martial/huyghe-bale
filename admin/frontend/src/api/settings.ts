import { get, put } from "./client";

export interface Settings {
  osc_frequency: number;
  output_cap: number;
}

export function getSettings() {
  return get<Settings>("/settings");
}

export function updateSettings(data: Partial<Settings>) {
  return put<Settings>("/settings", data);
}
