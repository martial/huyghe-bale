import { get, post } from "./client";
import type { BridgeState, BridgeEvent } from "../types/bridge";

export function getBridgeState() {
  return get<BridgeState>("/bridge/state");
}

export function clearBridgeEvents() {
  return post<{ ok: boolean }>("/bridge/clear");
}

/** Subscribe to the bridge SSE feed. Calls onEvent for every OSC message
 *  the bridge receives (including the backlog replay sent on connect).
 *  Returns a cleanup function.
 */
export function subscribeBridgeStream(
  onEvent: (event: BridgeEvent) => void,
  onError?: (e: Event) => void,
): () => void {
  const src = new EventSource("/api/v1/bridge/stream");
  src.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data) as BridgeEvent);
    } catch {
      /* malformed frame, skip */
    }
  };
  if (onError) src.onerror = onError;
  return () => src.close();
}
