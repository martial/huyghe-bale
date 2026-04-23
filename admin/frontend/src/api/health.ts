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
}

export interface HealthStatus {
  osc_receiver: OscReceiverStatus;
  bridge: BridgeStatus;
  playback: PlaybackStatus;
  vents_over_temp: VentsOverTempItem[];
  log_path: string | null;
  ok: boolean;
}

export function getHealth(): Promise<HealthStatus> {
  return get<HealthStatus>("/health");
}
