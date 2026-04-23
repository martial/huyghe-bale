import { useState, useEffect, useRef } from "react";
import { usePlaybackStore } from "../../stores/playback-store";

/**
 * Returns a smoothly-interpolated elapsed time (60fps via rAF)
 * that resyncs with the server on each 500ms poll.
 * Stops animating when paused.
 */
export function useSmoothedElapsed(): number {
  const status = usePlaybackStore((s) => s.status);
  const [elapsed, setElapsed] = useState(status.elapsed);
  const syncRef = useRef({ elapsed: status.elapsed, time: performance.now() });
  const rafRef = useRef(0);

  // Resync anchor whenever the server sends a new elapsed value
  useEffect(() => {
    syncRef.current = { elapsed: status.elapsed, time: performance.now() };
    if (!status.playing || status.paused) {
      setElapsed(status.elapsed);
    }
  }, [status.elapsed, status.playing, status.paused]);

  // Animate at 60fps while playing and not paused
  useEffect(() => {
    if (!status.playing || status.paused) {
      cancelAnimationFrame(rafRef.current);
      return;
    }

    function tick() {
      const dt = (performance.now() - syncRef.current.time) / 1000;
      const smoothed = syncRef.current.elapsed + dt;
      setElapsed(smoothed);
      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [status.playing, status.paused]);

  return elapsed;
}
