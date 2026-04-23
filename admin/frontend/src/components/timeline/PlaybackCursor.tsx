import { memo, useEffect, useRef } from "react";
import type { CanvasState } from "../../lib/timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import { usePlaybackStore } from "../../stores/playback-store";

/**
 * Playback cursor animated imperatively via refs — no React state, no
 * re-renders during playback. The rAF tick reads the store directly
 * (bypassing Zustand subscriptions) and writes `x1`/`x2`/`points`
 * attributes straight onto the SVG nodes. Browser does a partial
 * repaint of the cursor region only; the enclosing lane paths and
 * ruler ticks never touch React's reconciler.
 */
interface Props {
  canvas: CanvasState;
  height: number;
  /** Show the little triangle handle at y=0 (ruler only, not lane). */
  withHandle?: boolean;
  color?: string;
  strokeWidth?: number;
}

function PlaybackCursorImpl({
  canvas,
  height,
  withHandle = false,
  color = "#facc15",
  strokeWidth = 1.5,
}: Props) {
  const lineRef = useRef<SVGLineElement>(null);
  const polyRef = useRef<SVGPolygonElement>(null);
  const anchorRef = useRef({ elapsed: 0, time: performance.now() });

  useEffect(() => {
    // Prime the anchor + position synchronously from the current store
    // state so the cursor doesn't flash at x=0 before the first rAF.
    const s = usePlaybackStore.getState().status;
    anchorRef.current = { elapsed: s.elapsed, time: performance.now() };
    write(s.elapsed);

    // The server's reported `elapsed` trails our client-side extrapolation by
    // roughly one poll's worth of network / queuing latency. Resyncing on every
    // poll snaps the cursor backward → sawtooth lag. Resync ONLY on explicit
    // discontinuities (play/pause/stop/new-timeline/seek > 0.5 s), and let the
    // smooth rAF extrapolation carry us between them.
    const SEEK_THRESHOLD_S = 0.5;
    const unsubscribe = usePlaybackStore.subscribe((state, prev) => {
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
        // Paint once on pause/stop/seek so the cursor lands on the authoritative frame.
        if (!cur.playing || cur.paused) {
          write(cur.elapsed);
        }
      }
      // else: ordinary 500 ms poll, server slightly behind us — keep drifting.
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
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas]);

  function write(elapsed: number) {
    const x = tc.timeToX(canvas, elapsed);
    const xs = String(x);
    if (lineRef.current) {
      lineRef.current.setAttribute("x1", xs);
      lineRef.current.setAttribute("x2", xs);
    }
    if (polyRef.current) {
      polyRef.current.setAttribute("points", `${x - 4},0 ${x + 4},0 ${x},6`);
    }
  }

  return (
    <g pointerEvents="none">
      <line
        ref={lineRef}
        y1={0}
        y2={height}
        stroke={color}
        strokeWidth={strokeWidth}
        opacity={0.8}
      />
      {withHandle && (
        <polygon
          ref={polyRef}
          fill={color}
          opacity={0.9}
          className="cursor-col-resize"
        />
      )}
    </g>
  );
}

export const PlaybackCursor = memo(PlaybackCursorImpl);
