export type VentsMode = "raw" | "auto";
export type VentsState =
  | "idle"
  | "heating"
  | "cooling"
  | "holding"
  | "sensor_error"
  | "over_temp";

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
  max_temp_c?: number | null;
  mode: VentsMode;
  state: VentsState;
  timestamp?: number;
  online: boolean;
}
