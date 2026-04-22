import { useEffect, useState } from "react";

const POLL_MS = 700;
const STALE_AFTER_S = 3;

export interface PolledStatusSnapshot<T> {
  status: T | null;
  stale: boolean;
  lastPushAgeS: number | null;
}

/**
 * Poll a per-device status endpoint and compute a staleness flag.
 *
 * A status is "stale" when the device reports `online: true` but we haven't
 * received a new push from it within STALE_AFTER_S seconds — catches dropped
 * Wi-Fi / frozen broadcaster without a full offline transition.
 *
 * Used by both VentsTestPanel + VentsHero (via useVentsStatus) and the
 * trolley equivalents. One hook invocation per card — shared across the
 * hero and the detail panel so we don't double the poll rate.
 */
export function usePolledStatus<T extends { online: boolean; timestamp?: number }>(
  deviceId: string,
  fetcher: (id: string) => Promise<T>,
): PolledStatusSnapshot<T> {
  const [status, setStatus] = useState<T | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const s = await fetcher(deviceId);
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
    // fetcher is a module-level function passed stably from the call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const lastPushAgeS =
    status?.timestamp != null ? nowMs / 1000 - status.timestamp : null;
  const online = status?.online ?? false;
  const stale =
    online && (lastPushAgeS == null || lastPushAgeS > STALE_AFTER_S);

  return { status, stale, lastPushAgeS };
}
