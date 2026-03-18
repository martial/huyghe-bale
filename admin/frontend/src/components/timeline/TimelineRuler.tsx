import { useMemo, useRef, useCallback } from "react";
import type { CanvasState } from "../../lib/timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import { usePlaybackStore } from "../../stores/playback-store";
import { useSmoothedElapsed } from "../../hooks/use-smoothed-elapsed";

interface Props {
  width: number;
  height: number;
  duration: number;
  canvas: CanvasState;
  timelineId: string;
}

export default function TimelineRuler({ width, height, duration, canvas, timelineId }: Props) {
  const playbackStatus = usePlaybackStore((s) => s.status);
  const seek = usePlaybackStore((s) => s.seek);
  const smoothElapsed = useSmoothedElapsed();
  const showCursor = playbackStatus.playing && playbackStatus.id === timelineId && playbackStatus.type === "timeline";
  const cursorX = showCursor ? tc.timeToX(canvas, smoothElapsed) : 0;
  const svgRef = useRef<SVGSVGElement>(null);

  const seekToX = useCallback(
    (clientX: number) => {
      if (!svgRef.current || !showCursor) return;
      const rect = svgRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const time = Math.max(0, Math.min(duration, tc.xToTime(canvas, x)));
      seek(time);
    },
    [canvas, duration, seek, showCursor],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!showCursor) return;
      seekToX(e.clientX);

      const onMove = (me: MouseEvent) => seekToX(me.clientX);
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [seekToX, showCursor],
  );

  const ticks = useMemo(() => {
    const result: { x: number; label: string; major: boolean }[] = [];
    const pw = tc.plotWidth(canvas);
    const pixelsPerSecond = pw / duration;
    let interval = 1;
    if (pixelsPerSecond < 5) interval = 30;
    else if (pixelsPerSecond < 10) interval = 15;
    else if (pixelsPerSecond < 20) interval = 10;
    else if (pixelsPerSecond < 50) interval = 5;
    else interval = 1;

    for (let t = 0; t <= duration; t += interval) {
      const x = tc.timeToX(canvas, t);
      if (x < 48 || x > width - 16) continue;
      const minutes = Math.floor(t / 60);
      const seconds = t % 60;
      const label = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, "0")}` : `${seconds}s`;
      result.push({ x, label, major: t % (interval * 5) === 0 || t === 0 });
    }
    return result;
  }, [canvas, duration, width]);

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className={`bg-zinc-900/30 border-b border-zinc-800/60 overflow-hidden ${showCursor ? "cursor-col-resize" : ""}`}
      onMouseDown={handleMouseDown}
    >
      {ticks.map((tick) => (
        <g key={tick.x}>
          <line
            x1={tick.x}
            y1={tick.major ? 14 : 20}
            x2={tick.x}
            y2={height}
            stroke="#3f3f46"
            strokeWidth={1}
          />
          {tick.major && (
            <text
              x={tick.x}
              y={12}
              fill="#71717a"
              fontSize={9}
              textAnchor="middle"
              fontFamily="monospace"
            >
              {tick.label}
            </text>
          )}
        </g>
      ))}

      {/* Playback cursor */}
      {showCursor && (
        <g>
          <line
            x1={cursorX}
            y1={0}
            x2={cursorX}
            y2={height}
            stroke="#facc15"
            strokeWidth={1.5}
            opacity={0.8}
          />
          <polygon
            points={`${cursorX - 4},0 ${cursorX + 4},0 ${cursorX},6`}
            fill="#facc15"
            opacity={0.9}
            className="cursor-col-resize"
          />
        </g>
      )}
    </svg>
  );
}
