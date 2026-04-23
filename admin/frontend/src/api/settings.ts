import { get, put } from "./client";

export type BridgeRouting = "passthrough" | "type-match" | "none";

export interface Settings {
  osc_frequency: number;
  output_cap: number;
  bridge_enabled: boolean;
  bridge_port: number;
  bridge_routing: BridgeRouting;
  /** Absolute °C — over-temp threshold; saved to each vents Pi on Save */
  vents_max_temp_c: number;
}

export function getSettings() {
  return get<Settings>("/settings");
}

export function updateSettings(data: Partial<Settings>) {
  return put<Settings>("/settings", data);
}
