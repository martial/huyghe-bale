import { useCallback, useMemo, useRef } from "react";
import type { CanvasState } from "./lib/canvas-math";
import * as tc from "./lib/canvas-math";
import { usePlaybackStore } from "../stores/playback-store";
import { PlaybackCursor } from "./PlaybackCursor";

interface Props {
  canvas: CanvasState;
  height: number;
  duration: number;
  showCursor: boolean;
}

/**
 * Ruler with nicely-spaced tick labels and click/drag to seek while
 * playing. Hosts the shared PlaybackCursor inside its SVG.
 */
export default function Ruler({ canvas, height, duration, showCursor }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const seek = usePlaybackStore((s) => s.seek);

  const ticks = useMemo(() => {
    const out: { x: number; label: string; major: boolean }[] = [];
    const pw = tc.plotWidth(canvas);
    const pxPerSec = pw / duration;
    let interval = 1;
    if (pxPerSec < 5) interval = 30;
    else if (pxPerSec < 10) interval = 15;
    else if (pxPerSec < 20) interval = 10;
    else if (pxPerSec < 50) interval = 5;
    for (let t = 0; t <= duration; t += interval) {
      const x = tc.timeToX(canvas, t);
      if (x < canvas.paddingLeft || x > canvas.width - canvas.paddingRight) continue;
      const m = Math.floor(t / 60);
      const s = t % 60;
      out.push({
        x,
        label: m > 0 ? `${m}:${s.toString().padStart(2, "0")}` : `${s}s`,
        major: t % (interval * 5) === 0 || t === 0,
      });
    }
    return out;
  }, [canvas, duration]);

  const seekToX = useCallback(
    (clientX: number) => {
      if (!svgRef.current || !showCursor) return;
      const rect = svgRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      seek(Math.max(0, Math.min(duration, tc.xToTime(canvas, x))));
    },
    [canvas, duration, seek, showCursor],
  );

  function handleMouseDown(e: React.MouseEvent) {
    if (!showCursor) return;
    seekToX(e.clientX);
    const onMove = (me: MouseEvent) => seekToX(me.clientX);
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <svg
      ref={svgRef}
      width={canvas.width}
      height={height}
      className={`bg-zinc-900/30 border-b border-zinc-800/60 overflow-hidden ${
        showCursor ? "cursor-col-resize" : ""
      }`}
      onMouseDown={handleMouseDown}
    >
      {ticks.map((t) => (
        <g key={t.x}>
          <line
            x1={t.x}
            y1={t.major ? 14 : 20}
            x2={t.x}
            y2={height}
            stroke="#3f3f46"
            strokeWidth={1}
          />
          {t.major && (
            <text x={t.x} y={12} fill="#71717a" fontSize={9} textAnchor="middle" fontFamily="monospace">
              {t.label}
            </text>
          )}
        </g>
      ))}
      {showCursor && (
        <PlaybackCursor timeToX={(t) => tc.timeToX(canvas, t)} height={height} withHandle />
      )}
    </svg>
  );
}
