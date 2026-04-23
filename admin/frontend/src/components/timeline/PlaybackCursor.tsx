import { memo } from "react";
import type { CanvasState } from "../../lib/timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import { useSmoothedElapsed } from "../../hooks/use-smoothed-elapsed";

/**
 * Playback cursor isolated into its own component so the 60 Hz rAF
 * updates from `useSmoothedElapsed` re-render only this tiny tree —
 * not the ruler's ticks or the lane's curve / points.
 *
 * Render output is just `<line>` + optional `<polygon>`; the parent
 * decides whether to mount it (e.g. `{showCursor && <PlaybackCursor …/>}`)
 * based on `status.playing && status.id === timelineId`.
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
  const elapsed = useSmoothedElapsed();
  const x = tc.timeToX(canvas, elapsed);
  return (
    <g pointerEvents="none">
      <line
        x1={x}
        y1={0}
        x2={x}
        y2={height}
        stroke={color}
        strokeWidth={strokeWidth}
        opacity={0.8}
      />
      {withHandle && (
        <polygon
          points={`${x - 4},0 ${x + 4},0 ${x},6`}
          fill={color}
          opacity={0.9}
          className="cursor-col-resize"
        />
      )}
    </g>
  );
}

export const PlaybackCursor = memo(PlaybackCursorImpl);
