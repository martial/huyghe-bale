import { get } from "./client";

interface OscReceiverStatus {
  running: boolean;
  port: number;
  error: string | null;
}

interface BridgeStatus {
  running: boolean;
  port: number | null;
  error: string | null;
}

interface PlaybackStatus {
  thread_alive: boolean;
  playing: boolean;
  last_error: string | null;
}

export interface VentsOverTempItem {
  device_id: string;
  name: string;
  temp1_c?: number | null;
  temp2_c?: number | null;
  target_c?: number;
  max_temp_c?: number | null;
  /** Dual-setpoint fields (new firmware). Optional so the type stays
   *  compatible with old admin builds talking to old firmware. */
  temp_hot_c?: number | null;
  temp_cold_c?: number | null;
  hot_target_c?: number;
  cold_target_c?: number;
}

export interface VentsProbeUnassignedItem {
  device_id: string;
  name: string;
  probe_hot_id: string | null;
  probe_cold_id: string | null;
  /** ROM ids of every probe currently on the bus. The operator picks
   *  among these in the touch-test panel. */
  discovered: string[];
}

export interface HealthStatus {
  osc_receiver: OscReceiverStatus;
  bridge: BridgeStatus;
  playback: PlaybackStatus;
  vents_over_temp: VentsOverTempItem[];
  vents_probe_unassigned?: VentsProbeUnassignedItem[];
  log_path: string | null;
  ok: boolean;
}

export function getHealth(): Promise<HealthStatus> {
  return get<HealthStatus>("/health");
}
