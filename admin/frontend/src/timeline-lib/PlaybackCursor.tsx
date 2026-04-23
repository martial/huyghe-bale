import { memo, useEffect, useRef } from "react";
import { usePlaybackStore } from "../stores/playback-store";

/**
 * Shared playback cursor — imperative refs, no React state, no rerenders
 * during playback. The rAF tick reads the store directly (bypassing
 * Zustand subscriptions) and writes `x1`/`x2`/`points` attributes
 * straight onto the SVG nodes. Browser does a partial repaint of the
 * cursor region only; the enclosing track paths / ticks never touch
 * React's reconciler.
 *
 * Used by every track in the timeline library. The caller supplies a
 * `timeToX(elapsed): px` mapping (continuous curve, event-track, etc.)
 * so the cursor is agnostic to the track's layout maths.
 */
interface Props {
  /** Convert elapsed time (seconds) to the cursor's x in local px. */
  timeToX: (elapsed: number) => number;
  /** SVG local height for the line. */
  height: number;
  /** Show the little triangle handle at y=0 (ruler only). */
  withHandle?: boolean;
  color?: string;
  strokeWidth?: number;
}

function PlaybackCursorImpl({
  timeToX,
  height,
  withHandle = false,
  color = "#facc15",
  strokeWidth = 1.5,
}: Props) {
  const lineRef = useRef<SVGLineElement>(null);
  const polyRef = useRef<SVGPolygonElement>(null);
  const anchorRef = useRef({ elapsed: 0, time: performance.now() });

  useEffect(() => {
    const s = usePlaybackStore.getState().status;
    console.log("[PlaybackCursor] mount — priming anchor", {
      elapsed: s.elapsed,
      playing: s.playing,
      id: s.id,
    });
    anchorRef.current = { elapsed: s.elapsed, time: performance.now() };
    write(s.elapsed);

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
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeToX]);

  function write(elapsed: number) {
    const x = timeToX(elapsed);
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
