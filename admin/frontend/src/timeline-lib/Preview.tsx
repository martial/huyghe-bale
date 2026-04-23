import { useEffect, useState } from "react";
import type { UniversalTimeline } from "./types";
import { sampleCurve } from "./lib/interpolation";
import { ventsTimelineToUniversal } from "./adapters/vents";
import { trolleyTimelineToUniversal } from "./adapters/trolley";
import { getTimeline } from "../api/timelines";
import { getTrolleyTimeline } from "../api/trolley";
import type { TimelineKind } from "./types";

interface Props {
  id: string;
  kind: TimelineKind;
  width?: number;
  height?: number;
}

/** Tiny SVG thumbnail that works for both curve timelines (paths) and
 *  bang timelines (tick-per-event density strip). */
export default function Preview({ id, kind, width = 128, height = 64 }: Props) {
  const [tl, setTl] = useState<UniversalTimeline | null>(null);

  useEffect(() => {
    let cancelled = false;
    const p =
      kind === "vents"
        ? getTimeline(id).then(ventsTimelineToUniversal)
        : getTrolleyTimeline(id).then(trolleyTimelineToUniversal);
    p.then((t) => !cancelled && setTl(t)).catch(
      () => !cancelled && setTl(null),
    );
    return () => {
      cancelled = true;
    };
  }, [id, kind]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="bg-zinc-900 rounded">
      {tl?.tracks.map((track, i) => {
        if (track.kind === "curve") {
          return (
            <path
              key={track.id}
              d={curvePath(track.points, tl.duration, width, height)}
              fill="none"
              stroke={track.color}
              strokeWidth={1.5}
              opacity={0.75}
            />
          );
        }
        // Bang track: vertical tick per event.
        const y0 = (height / tl.tracks.length) * i + 8;
        const y1 = (height / tl.tracks.length) * (i + 1) - 8;
        return (
          <g key={track.id}>
            {track.events.map((ev) => {
              const x = (ev.time / Math.max(1, tl.duration)) * width;
              const cmd = track.commands.find((c) => c.command === ev.command);
              return (
                <line
                  key={ev.id}
                  x1={x}
                  y1={y0}
                  x2={x}
                  y2={y1}
                  stroke={cmd?.color ?? track.color}
                  strokeWidth={1.5}
                  opacity={0.85}
                />
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}

function curvePath(
  points: Array<{
    time: number;
    value: number;
    curveType: string;
    bezierHandles: { x1: number; y1: number; x2: number; y2: number } | null;
  }>,
  duration: number,
  width: number,
  height: number,
): string {
  if (points.length < 2) return "";
  let d = "";
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i]!;
    const p1 = points[i + 1]!;
    const x0 = (p0.time / duration) * width;
    const y0 = (1 - p0.value) * height;
    const x1 = (p1.time / duration) * width;
    const y1 = (1 - p1.value) * height;
    if (p1.curveType === "linear" || p1.curveType === "step") {
      if (i === 0) d += `M${x0},${y0}`;
      if (p1.curveType === "step") d += ` H${x1} V${y1}`;
      else d += ` L${x1},${y1}`;
    } else {
      if (i === 0) d += `M${x0},${y0}`;
      const samples = sampleCurve(
        p1.curveType as Parameters<typeof sampleCurve>[0],
        p1.bezierHandles,
        20,
      );
      for (const [t, v] of samples) {
        const sx = x0 + (x1 - x0) * t;
        const sv = p0.value + (p1.value - p0.value) * v;
        d += ` L${sx},${(1 - sv) * height}`;
      }
    }
  }
  return d;
}
