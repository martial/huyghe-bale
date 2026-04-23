import { memo, useEffect, useRef } from "react";
import { usePlaybackStore } from "../../stores/playback-store";

/**
 * Trolley playback cursor animated imperatively via a ref — zero React
 * renders during playback. Mirrors the pattern used in the vents
 * PlaybackCursor: rAF + Zustand `.subscribe` + direct `style.left` write.
 */
interface Props {
  /** Pixel offset of the event area from the strip's left edge. */
  labelColPx: number;
  /** Measured width (px) of the event area. */
  stripWidth: number;
  /** Timeline duration in seconds. */
  duration: number;
}

function TrolleyPlaybackCursorImpl({ labelColPx, stripWidth, duration }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const anchorRef = useRef({ elapsed: 0, time: performance.now() });

  useEffect(() => {
    const s = usePlaybackStore.getState().status;
    anchorRef.current = { elapsed: s.elapsed, time: performance.now() };
    write(s.elapsed);

    const SEEK_THRESHOLD_S = 0.5;
    const unsub = usePlaybackStore.subscribe((state, prev) => {
      const cur = state.status;
      const old = prev.status;
      const playingChanged = cur.playing !== old.playing;
      const pausedChanged = cur.paused !== old.paused;
      const idChanged = cur.id !== old.id;
      const extrapolated =
        anchorRef.current.elapsed +
        (performance.now() - anchorRef.current.time) / 1000;
      const drift = cur.elapsed - extrapolated;
      const looksLikeSeek = Math.abs(drift) > SEEK_THRESHOLD_S;
      if (playingChanged || pausedChanged || idChanged || looksLikeSeek) {
        anchorRef.current = { elapsed: cur.elapsed, time: performance.now() };
        if (!cur.playing || cur.paused) write(cur.elapsed);
      }
    });

    let raf = 0;
    function tick() {
      const { playing, paused } = usePlaybackStore.getState().status;
      if (playing && !paused) {
        const dt = (performance.now() - anchorRef.current.time) / 1000;
        write(anchorRef.current.elapsed + dt);
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      unsub();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labelColPx, stripWidth, duration]);

  function write(elapsed: number) {
    if (!ref.current || duration <= 0 || stripWidth <= 0) return;
    const pct = Math.max(0, Math.min(1, elapsed / duration));
    ref.current.style.left = `${labelColPx + pct * stripWidth}px`;
  }

  return (
    <div
      ref={ref}
      className="absolute top-0 bottom-0 w-px bg-green-400/70 shadow-[0_0_6px_rgba(74,222,128,0.5)] pointer-events-none"
      style={{ left: `${labelColPx}px` }}
    />
  );
}

export const TrolleyPlaybackCursor = memo(TrolleyPlaybackCursorImpl);
