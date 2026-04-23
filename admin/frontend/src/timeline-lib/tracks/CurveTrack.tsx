import { useMemo, useRef, useState, useCallback } from "react";
import type { CurveTrack as CurveTrackData, CurvePoint, CurveType } from "../types";
import type { CanvasState } from "../lib/canvas-math";
import * as tc from "../lib/canvas-math";
import { sampleCurve } from "../lib/interpolation";
import { PlaybackCursor } from "../PlaybackCursor";

interface Props {
  track: CurveTrackData;
  canvas: CanvasState;
  height: number;
  selectedPointId: string | null;
  showCursor: boolean;
  readonly?: boolean;
  onSelectPoint: (id: string | null) => void;
  onChange: (next: CurveTrackData) => void;
  onWheel?: (e: React.WheelEvent) => void;
}

const gridLines = [0, 0.25, 0.5, 0.75, 1.0];

function genId(): string {
  return "pt_" + Math.random().toString(36).substring(2, 10);
}

export default function CurveTrack({
  track,
  canvas,
  height,
  selectedPointId,
  showCursor,
  readonly = false,
  onSelectPoint,
  onChange,
  onWheel,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const width = canvas.width;

  const points = track.points;

  const segments = useMemo(() => {
    if (points.length < 2) return [] as { d: string }[];
    const out: { d: string }[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i]!;
      const p1 = points[i + 1]!;
      const x0 = tc.timeToX(canvas, p0.time);
      const y0 = tc.valueToY(canvas, p0.value);
      const x1 = tc.timeToX(canvas, p1.time);
      const y1 = tc.valueToY(canvas, p1.value);
      const ct = p1.curveType;
      if (ct === "linear") {
        out.push({ d: `M${x0},${y0} L${x1},${y1}` });
      } else if (ct === "step") {
        out.push({ d: `M${x0},${y0} H${x1} V${y1}` });
      } else if (ct === "bezier" && p1.bezierHandles) {
        const h = p1.bezierHandles;
        const cp1x = x0 + (x1 - x0) * h.x1;
        const cp1y = y0 - (y0 - y1) * h.y1;
        const cp2x = x0 + (x1 - x0) * h.x2;
        const cp2y = y0 - (y0 - y1) * h.y2;
        out.push({ d: `M${x0},${y0} C${cp1x},${cp1y} ${cp2x},${cp2y} ${x1},${y1}` });
      } else {
        let d = `M${x0},${y0}`;
        for (const [t, v] of sampleCurve(ct as CurveType, p1.bezierHandles)) {
          const sx = x0 + (x1 - x0) * t;
          const sv = p0.value + (p1.value - p0.value) * v;
          d += ` L${sx},${tc.valueToY(canvas, sv)}`;
        }
        out.push({ d });
      }
    }
    return out;
  }, [points, canvas]);

  const replacePoints = useCallback(
    (next: CurvePoint[]) => onChange({ ...track, points: next.sort((a, b) => a.time - b.time) }),
    [onChange, track],
  );

  const addPoint = useCallback(
    (time: number, value: number) => {
      const pt: CurvePoint = {
        id: genId(),
        time,
        value,
        curveType: "linear",
        bezierHandles: null,
      };
      const next = [...points, pt].sort((a, b) => a.time - b.time);
      onChange({ ...track, points: next });
      onSelectPoint(pt.id);
    },
    [points, onChange, track, onSelectPoint],
  );

  function handleSvgClick(e: React.MouseEvent<SVGSVGElement>) {
    if (readonly || dragId) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Ignore clicks on existing point markers (let the marker handler fire).
    for (const pt of points) {
      const px = tc.timeToX(canvas, pt.time);
      const py = tc.valueToY(canvas, pt.value);
      if (Math.hypot(px - x, py - y) < 12) return;
    }
    const time = Math.max(0, Math.min(canvas.duration, tc.xToTime(canvas, x)));
    const value = tc.yToValue(canvas, y);
    addPoint(time, value);
  }

  const startDrag = useCallback(
    (e: React.MouseEvent, point: CurvePoint) => {
      if (readonly) return;
      e.stopPropagation();
      e.preventDefault();
      onSelectPoint(point.id);
      setDragId(point.id);
      const svg = svgRef.current!;
      function onMove(me: MouseEvent) {
        const rect = svg.getBoundingClientRect();
        const mx = me.clientX - rect.left;
        const my = me.clientY - rect.top;
        const t = Math.max(0, Math.min(canvas.duration, tc.xToTime(canvas, mx)));
        const v = tc.yToValue(canvas, my);
        onChange({
          ...track,
          points: points
            .map((p) => (p.id === point.id ? { ...p, time: t, value: v } : p))
            .sort((a, b) => a.time - b.time),
        });
      }
      function onUp() {
        setDragId(null);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      }
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [canvas, onChange, onSelectPoint, points, readonly, track],
  );

  function handleMarkerClick(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    onSelectPoint(id);
  }

  function handleMarkerDblClick(e: React.MouseEvent, id: string) {
    if (readonly) return;
    e.stopPropagation();
    replacePoints(points.filter((p) => p.id !== id));
    onSelectPoint(null);
  }

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="bg-zinc-950/20 select-none cursor-crosshair"
      onClick={handleSvgClick}
      onWheel={onWheel}
    >
      {/* Value grid lines */}
      {gridLines.map((v) => {
        const y = tc.valueToY(canvas, v);
        return (
          <g key={v}>
            <line
              x1={canvas.paddingLeft}
              x2={width - canvas.paddingRight}
              y1={y}
              y2={y}
              stroke={v === 0 || v === 1 ? "#3f3f46" : "#27272a"}
              strokeDasharray={v === 0 || v === 1 ? undefined : "2 4"}
              strokeWidth={1}
            />
            <text x={8} y={y + 3} fill="#52525b" fontSize={9} fontFamily="monospace">
              {v.toFixed(2)}
            </text>
          </g>
        );
      })}

      {/* Curve */}
      {segments.map((s, i) => (
        <path key={i} d={s.d} fill="none" stroke={track.color} strokeWidth={2} opacity={0.9} />
      ))}

      {showCursor && (
        <PlaybackCursor timeToX={(t) => tc.timeToX(canvas, t)} height={height} />
      )}

      {/* Point markers */}
      {points.map((pt) => {
        const cx = tc.timeToX(canvas, pt.time);
        const cy = tc.valueToY(canvas, pt.value);
        const selected = pt.id === selectedPointId;
        const hovered = pt.id === hoverId;
        return (
          <circle
            key={pt.id}
            cx={cx}
            cy={cy}
            r={selected ? 6 : hovered ? 5 : 4}
            fill={selected ? "#fff" : track.color}
            stroke={track.color}
            strokeWidth={selected ? 2 : 1}
            className={readonly ? "cursor-not-allowed" : "cursor-grab active:cursor-grabbing"}
            onMouseEnter={() => setHoverId(pt.id)}
            onMouseLeave={() => setHoverId((h) => (h === pt.id ? null : h))}
            onMouseDown={(e) => startDrag(e, pt)}
            onClick={(e) => handleMarkerClick(e, pt.id)}
            onDoubleClick={(e) => handleMarkerDblClick(e, pt.id)}
          >
            <title>
              t={pt.time.toFixed(2)}s v={pt.value.toFixed(3)} · {pt.curveType}
              {readonly ? "" : " · double-click to delete"}
            </title>
          </circle>
        );
      })}
    </svg>
  );
}
