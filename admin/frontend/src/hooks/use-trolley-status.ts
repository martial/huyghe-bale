import { useEffect, useState } from "react";
import type { TrolleyStatus } from "../types/trolley";
import { fetchTrolleyStatus } from "../api/trolley";

const POLL_MS = 700;
const STALE_AFTER_S = 3;

export interface TrolleyStatusSnapshot {
  status: TrolleyStatus | null;
  stale: boolean;
  lastPushAgeS: number | null;
}

/** Poll a trolley device's status + compute a staleness flag. */
export function useTrolleyStatus(deviceId: string): TrolleyStatusSnapshot {
  const [status, setStatus] = useState<TrolleyStatus | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetchTrolleyStatus(deviceId);
        if (!cancelled) setStatus(s);
      } catch {
        /* transient */
      }
    }
    poll();
    const pollTimer = setInterval(poll, POLL_MS);
    const staleTick = setInterval(() => setNowMs(Date.now()), 1000);
    return () => {
      cancelled = true;
      clearInterval(pollTimer);
      clearInterval(staleTick);
    };
  }, [deviceId]);

  const lastPushAgeS =
    status?.timestamp != null ? nowMs / 1000 - status.timestamp : null;
  const online = status?.online ?? false;
  const stale =
    online && (lastPushAgeS == null || lastPushAgeS > STALE_AFTER_S);

  return { status, stale, lastPushAgeS };
}
