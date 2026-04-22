import { useEffect, useState } from "react";
import type { VentsStatus } from "../types/vents";
import { fetchVentsStatus } from "../api/vents";

const POLL_MS = 700;
const STALE_AFTER_S = 3;

export interface VentsStatusSnapshot {
  status: VentsStatus | null;
  stale: boolean;
  lastPushAgeS: number | null;
}

/** Poll a vents device's status + compute a staleness flag.
 *  One hook call per card — share between Hero and TestPanel. */
export function useVentsStatus(deviceId: string): VentsStatusSnapshot {
  const [status, setStatus] = useState<VentsStatus | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetchVentsStatus(deviceId);
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
