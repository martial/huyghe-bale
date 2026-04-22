import type { BridgeRouting } from "../api/settings";

export type { BridgeRouting };

export interface BridgeEvent {
  t: number;          // unix seconds
  src: string;        // source IP
  address: string;    // OSC address as received
  args: unknown[];
  targets: string[];  // device ids that received a forwarded copy
  /** If the incoming address was `/to/<id>/<rest>`, this is the unwrapped `<rest>`
   *  that was actually sent to the device. Absent for normal routing. */
  forwarded_as?: string;
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
