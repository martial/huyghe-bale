import { get, put } from "./client";

export type BridgeRouting = "passthrough" | "type-match" | "none";

export interface Settings {
  osc_frequency: number;
  bridge_enabled: boolean;
  bridge_port: number;
  bridge_routing: BridgeRouting;
  /** Absolute °C — over-temp threshold; saved to each vents Pi on Save */
  vents_max_temp_c: number;
  /** PWM floor (% duty) every vents Pi enforces on non-zero fan commands */
  vents_min_fan_pct: number;
  /** PWM scale (0–100). The Pi multiplies every non-zero fan command by this/100. */
  vents_max_fan_pct: number;
  /** Per-channel RPM threshold below which the admin raises an alarm */
  vents_min_rpm_alarm: number;
  /** Fan PWM (%) the Pi forces both fans to whenever any sensor exceeds max */
  vents_over_temp_fan_pct: number;
  /** Outbound webhook URL — empty disables. Receives status_change events. */
  webhook_url: string;
  /** Optional bearer token sent in Authorization header on every webhook POST. */
  webhook_token: string;
  /** When true, post a device_snapshot event every stats_webhook_interval_s seconds. */
  stats_webhook_enabled: boolean;
  /** Separate URL for periodic device-snapshot POSTs. Empty disables. */
  stats_webhook_url: string;
  /** Optional bearer token for snapshot POSTs. */
  stats_webhook_token: string;
  /** Snapshot interval in seconds (10–3600). */
  stats_webhook_interval_s: number;
}

export function getSettings() {
  return get<Settings>("/settings");
}

export function updateSettings(data: Partial<Settings>) {
  return put<Settings>("/settings", data);
}
