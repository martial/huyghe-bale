export type VentsMode = "raw" | "auto";
export type VentsState =
  | "idle"
  | "cooling"
  | "holding"
  | "coasting"
  | "sensor_error";

export type VentsCommand = "peltier" | "peltier_mask" | "fan" | "mode" | "target";

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
  mode: VentsMode;
  state: VentsState;
  timestamp?: number;
  online: boolean;
}
