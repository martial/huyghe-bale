export type TrolleyCommand =
  | "enable"
  | "dir"
  | "speed"
  | "accel"
  | "decel"
  | "step"
  | "stop"
  | "home"
  | "position"
  | "config_set"
  | "config_save"
  | "config_get";

export type TrolleyState = "idle" | "homing" | "following";

export type CalibrationDirection = "forward" | "reverse";

export interface TrolleySettings {
  rail_length_mm: number | null;
  wheel_radius_mm: number | null;
  steps_per_rev: number;
  microsteps: number;
  max_speed_hz: number;
  home_speed_hz: number;
  calibration_direction: CalibrationDirection;
  soft_limit_pct: number;
  accel_time_s: number;
  decel_time_s: number;
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
  /** 1 = rail length and wheel radius are set on the Pi; 0 = needs config. */
  calibrated: number;
  state: TrolleyState;
  timestamp?: number;
  online: boolean;
}
