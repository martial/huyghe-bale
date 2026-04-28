export type TrolleyCommand =
  | "enable"
  | "dir"
  | "speed"
  | "step"
  | "stop"
  | "home"
  | "position"
  | "calibrate_start"
  | "calibrate_stop"
  | "calibrate_save"
  | "calibrate_cancel"
  | "config_set"
  | "config_save"
  | "config_get";

export type TrolleyState = "idle" | "homing" | "following" | "calibrating";

export type CalibrationDirection = "forward" | "reverse";

export interface TrolleySettings {
  rail_length_steps: number | null;
  lead_mm_per_rev: number;
  steps_per_rev: number;
  microsteps: number;
  max_speed_hz: number;
  calibration_speed_hz: number;
  calibration_direction: CalibrationDirection;
  soft_limit_pct: number;
}

/** Subset of TrolleyCommand that can appear in a timeline. Calibration and
 *  config commands are admin-only and never scheduled on a timeline. */
export type TimelineTrolleyCommand =
  | "enable"
  | "dir"
  | "speed"
  | "step"
  | "stop"
  | "home"
  | "position";

export interface TrolleyEvent {
  id: string;
  time: number;
  command: TimelineTrolleyCommand;
  value?: number;
}

export interface TrolleyTimeline {
  id: string;
  name: string;
  duration: number;
  created_at?: string;
  events: TrolleyEvent[];
  /** Built-in example — API rejects PUT/DELETE. Edit via Duplicate. */
  readonly?: boolean;
}

export interface TrolleyTimelineSummary {
  id: string;
  name: string;
  duration: number;
  events: number;
  created_at?: string;
  readonly?: boolean;
}

export interface TrolleyStatus {
  position: number;
  limit: number;
  homed: number;
  /** 1 = rail_length_steps is set on the Pi; 0 = needs calibration. */
  calibrated: number;
  state: TrolleyState;
  timestamp?: number;
  online: boolean;
}
