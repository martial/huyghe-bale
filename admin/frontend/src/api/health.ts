import { get } from "./client";

interface OscReceiverStatus {
  running: boolean;
  port: number;
  error: string | null;
}

export interface HealthStatus {
  osc_receiver: OscReceiverStatus;
}

export function getHealth(): Promise<HealthStatus> {
  return get<HealthStatus>("/health");
}
