export type VentsMode = "raw" | "auto";
export type VentsState =
  | "idle"
  | "heating"
  | "holding"
  | "sensor_error"
  | "probe_unassigned"
  | "over_temp"
  /** Unique-peltier auto sub-mode: regulator wants to drive on, but every
   *  cell is still inside its minimum-OFF cooldown — nothing can be driven
   *  until at least one cell becomes eligible. Distinct from "holding"
   *  (deadband, mask unchanged). */
  | "rest_wait";

export type VentsCommand =
  | "peltier"
  | "peltier_mask"
  | "fan"
  | "mode"
  | "target"
  | "target_hot"
  | "target_cold"
  | "target_active"
  | "max_temp"
  | "probe_assign_hot"
  | "probe_assign_cold"
  | "probe_clear"
  | "unique_peltier"
  | "peltier_rest_s";

/** Which side currently regulates in auto mode. The other setpoint is stored
 *  but inactive (greyed out in the UI). Set by the most recent setpoint write
 *  or explicitly via `setVentsActiveTarget`. Default on a fresh install is "hot". */
export type VentsActiveTarget = "hot" | "cold";

/** A DS18B20 probe discovered on the 1-Wire bus. `id` is the 64-bit ROM
 *  serial (`28-xxxxxxxxxxxx`) — stable across boots, used to pin the probe
 *  to its physical role (hot face vs cold face). `temp_c` is the most
 *  recent reading (null on parse/IO failure). */
export interface VentsProbe {
  id: string;
  temp_c: number | null;
}

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
  /** Back-compat alias for `hot_target_c`. Always equals it on new firmware. */
  target_c: number;
  /** Hot-side regulation setpoint (°C). Regulates the probe assigned to the
   *  hot face. */
  hot_target_c?: number;
  /** Cold-side regulation setpoint (°C). Regulates the probe assigned to the
   *  cold face. */
  cold_target_c?: number;
  /** Which side currently regulates. Absent on pre-active-target firmware —
   *  the UI falls back to "hot" so existing devices keep showing hot as live. */
  active_target?: VentsActiveTarget;
  /** Live reading from the probe assigned to hot face. Null when the probe is
   *  unassigned or its assigned ROM id isn't currently on the bus. */
  temp_hot_c?: number | null;
  /** Live reading from the probe assigned to cold face. Same null rules. */
  temp_cold_c?: number | null;
  /** ROM id of the probe assigned to hot. Null = unassigned. */
  probe_hot_id?: string | null;
  /** ROM id of the probe assigned to cold. Null = unassigned. */
  probe_cold_id?: string | null;
  /** Every DS18B20 currently discovered on the bus. Drives the probe
   *  assignment UI. Absent on legacy firmware (the panel hides itself). */
  probes?: VentsProbe[];
  max_temp_c?: number | null;
  /** PWM floor (% duty) the Pi enforces on every non-zero fan command. */
  min_fan_pct?: number | null;
  /** PWM scale (0–100). The Pi multiplies every non-zero fan command by this/100. */
  max_fan_pct?: number | null;
  /** Fan PWM (%) the Pi forces on both fans during the over-temp interlock. */
  over_temp_fan_pct?: number | null;
  /** Unique-peltier auto sub-mode flag (0|1). Absent on pre-unique firmware. */
  unique_peltier?: number;
  /** Per-cell minimum-OFF cooldown in seconds (shared threshold; the cells'
   *  timers are tracked independently). Absent on pre-unique firmware. */
  peltier_rest_s?: number;
  /** Index of the cell currently being driven in unique mode (0..2). -1 when
   *  no cell is driven (rest_wait, drive-off branch of heating, holding-off,
   *  or unique mode off). */
  active_peltier_index?: number;
  /** Per-cell remaining seconds before each cell becomes eligible in unique
   *  mode. Always length 3 when present. 0 means eligible now (or never-run).
   *  HTTP-snapshot only — not in the 5 Hz OSC broadcast. */
  peltier_rest_remaining?: number[];
  mode: VentsMode;
  state: VentsState;
  timestamp?: number;
  online: boolean;
}
