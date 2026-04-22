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

export interface HealthStatus {
  osc_receiver: OscReceiverStatus;
  bridge: BridgeStatus;
  playback: PlaybackStatus;
  log_path: string | null;
  ok: boolean;
}

export function getHealth(): Promise<HealthStatus> {
  return get<HealthStatus>("/health");
}
