export type VentsMode = "raw" | "auto";
export type VentsState =
  | "idle"
  | "heating"
  | "cooling"
  | "holding"
  | "sensor_error"
  | "over_temp";

export type VentsCommand = "peltier" | "peltier_mask" | "fan" | "mode" | "target";

/** Display labels for the four fan-tach channels echoed in /vents/status.
 *  Channels 0/1 → fan 1's two tachometer signals; 2/3 → fan 2's two. */
export const VENTS_TACH_CHANNEL_LABEL: Record<number, string> = {
  0: "Fan 1 tach A",
  1: "Fan 1 tach B",
  2: "Fan 2 tach A",
  3: "Fan 2 tach B",
};

export interface VentsStatus {
  temp1_c: number | null;
  temp2_c: number | null;
  fan1: number;
  fan2: number;
  peltier_mask: number;
  peltier: boolean[];
  rpm1A: number;
  rpm1B: number;
  rpm2A: number;
  rpm2B: number;
  target_c: number;
  max_temp_c?: number | null;
  /** PWM floor (% duty) the Pi enforces on every non-zero fan command. */
  min_fan_pct?: number | null;
  /** PWM scale (0–100). The Pi multiplies every non-zero fan command by this/100. */
  max_fan_pct?: number | null;
  /** Fan PWM (%) the Pi forces on both fans during the over-temp interlock. */
  over_temp_fan_pct?: number | null;
  mode: VentsMode;
  state: VentsState;
  timestamp?: number;
  online: boolean;
}
