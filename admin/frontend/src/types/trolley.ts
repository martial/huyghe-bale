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
  | "config_get"
  | "alarm_reset";

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
  limit_switches_swapped: boolean;
  soft_limit_pct: number;
  permissive_mode: boolean;
  accel_time_s: number;
  decel_time_s: number;
  /** Derived on the Pi from rail_length_mm + wheel_radius_mm + steps. */
  rail_length_steps?: number;
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
  /** 1 = at least one driver alarm pin is currently asserted. */
  alarm?: number;
  /** 1 = the firmware has latched the alarm lock and is refusing motion. */
  alarm_locked?: number;
  /** 1 = ENA is asserted (driver energized). Sourced from the Pi's status
   *  broadcast so the admin reflects the live driver state, not a local cache. */
  enabled?: number;
  /** Last-applied speed scaled 0..1 of MAX_HZ. Echo of `/trolley/speed`. */
  speed_pct?: number | null;
  /** Last-applied direction (0=reverse, 1=forward). Echo of `/trolley/dir`. */
  dir?: number | null;
  /** Live accel ramp time on the Pi, seconds. Echo of `/trolley/accel`. */
  accel_time_s?: number | null;
  /** Live decel ramp time on the Pi, seconds. Echo of `/trolley/decel`. */
  decel_time_s?: number | null;
  timestamp?: number;
  online: boolean;
}
