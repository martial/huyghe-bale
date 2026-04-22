import type { BridgeRouting } from "../api/settings";

export type { BridgeRouting };

export interface BridgeEvent {
  t: number;          // unix seconds
  src: string;        // source IP
  address: string;    // OSC address
  args: unknown[];
  targets: string[];  // device ids that received a forwarded copy
  dropped?: string;   // if present, the event was NOT forwarded and this is why
}

export interface BridgeState {
  enabled: boolean;
  running: boolean;
  port: number;
  routing: BridgeRouting;
  error: string | null;
  events: BridgeEvent[];
}
