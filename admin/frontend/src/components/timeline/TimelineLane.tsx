import { useState, useRef, useMemo, useCallback } from "react";
import type { Lane, Point } from "../../types/timeline";
import type { CanvasState } from "../../lib/timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import { sampleCurve } from "../../lib/interpolation";
import { usePlaybackStore } from "../../stores/playback-store";
import { useSmoothedElapsed } from "../../hooks/use-smoothed-elapsed";

interface Props {
  lane: Lane;
  width: number;
  height: number;
  canvas: CanvasState;
  selectedPointId: string | null;
  color: string;
  timelineId: string;
  playbackType?: "timeline" | "trolley-timeline";
  onSelectPoint: (id: string) => void;
  onAddPoint: (time: number, value: number, shiftKey: boolean) => void;
  onRemovePoint: (id: string) => void;
  onDragPoint: (id: string, time: number, value: number) => void;
  onDragBezierHandle: (pointId: string, handleIndex: 1 | 2, x: number, y: number) => void;
  onWheel: (e: React.WheelEvent) => void;
}

const gridLines = [0, 0.25, 0.5, 0.75, 1.0];

export default function TimelineLane({
  lane,
  width,
  height,
  canvas,
  selectedPointId,
  color,
  timelineId,
  playbackType = "timeline",
  onSelectPoint,
  onAddPoint,
  onRemovePoint,
  onDragPoint,
  onDragBezierHandle,
  onWheel,
}: Props) {
  const playbackStatus = usePlaybackStore((s) => s.status);
  const smoothElapsed = useSmoothedElapsed();
  const showCursor = playbackStatus.playing && playbackStatus.id === timelineId && playbackStatus.type === playbackType;
  const cursorX = showCursor ? tc.timeToX(canvas, smoothElapsed) : 0;
  const [hoveredPointId, setHoveredPointId] = useState<string | null>(null);
  const [dragPointId, setDragPointId] = useState<string | null>(null);
  const [dragHandleId, setDragHandleId] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const curveSegments = useMemo(() => {
    const pts = lane.points;
    if (pts.length < 2) return [];

    const segments: { pathD: string; curveType: string }[] = [];

    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i]!;
      const p1 = pts[i + 1]!;
      const x0 = tc.timeToX(canvas, p0.time);
      const y0 = tc.valueToY(canvas, p0.value);
      const x1 = tc.timeToX(canvas, p1.time);
      const y1 = tc.valueToY(canvas, p1.value);

      const ct = p1.curve_type;

      if (ct === "linear") {
        segments.push({ pathD: `M${x0},${y0} L${x1},${y1}`, curveType: ct });
      } else if (ct === "step") {
        segments.push({ pathD: `M${x0},${y0} H${x1} V${y1}`, curveType: ct });
      } else if (ct === "bezier" && p1.bezier_handles) {
        const h = p1.bezier_handles;
        const cp1x = x0 + (x1 - x0) * h.x1;
        const cp1y = y0 - (y0 - y1) * h.y1;
        const cp2x = x0 + (x1 - x0) * h.x2;
        const cp2y = y0 - (y0 - y1) * h.y2;
        segments.push({
          pathD: `M${x0},${y0} C${cp1x},${cp1y} ${cp2x},${cp2y} ${x1},${y1}`,
          curveType: ct,
        });
      } else {
        const samples = sampleCurve(ct, p1.bezier_handles);
        let d = `M${x0},${y0}`;
        for (const [t, v] of samples) {
          const sx = x0 + (x1 - x0) * t;
          const sv = p0.value + (p1.value - p0.value) * v;
          const sy = tc.valueToY(canvas, sv);
          d += ` L${sx},${sy}`;
        }
        segments.push({ pathD: d, curveType: ct });
      }
    }
    return segments;
  }, [lane.points, canvas]);

  function getPrevPoint(point: Point): Point | null {
    const idx = lane.points.indexOf(point);
    return idx > 0 ? lane.points[idx - 1]! : null;
  }

  const selectedBezierHandles = useMemo(() => {
    const point = lane.points.find((p) => p.id === selectedPointId);
    if (!point || point.curve_type !== "bezier" || !point.bezier_handles) return null;
    const idx = lane.points.indexOf(point);
    const prev = idx > 0 ? lane.points[idx - 1]! : null;
    if (!prev) return null;

    const h = point.bezier_handles;
    const x0 = tc.timeToX(canvas, prev.time);
    const y0 = tc.valueToY(canvas, prev.value);
    const x1 = tc.timeToX(canvas, point.time);
    const y1 = tc.valueToY(canvas, point.value);

    return {
      pointId: point.id,
      prevX: x0, prevY: y0,
      currX: x1, currY: y1,
      cp1x: x0 + (x1 - x0) * h.x1,
      cp1y: y0 - (y0 - y1) * h.y1,
      cp2x: x0 + (x1 - x0) * h.x2,
      cp2y: y0 - (y0 - y1) * h.y2,
    };
  }, [lane.points, selectedPointId, canvas]);

  const startHandleDrag = useCallback(
    (e: React.MouseEvent, point: Point, handleIndex: 1 | 2) => {
      e.preventDefault();
      e.stopPropagation();
      setDragHandleId(`${point.id}-cp${handleIndex}`);

      const svg = svgRef.current!;
      const prev = getPrevPoint(point);
      if (!prev || !point.bezier_handles) return;

      const onMove = (me: MouseEvent) => {
        const rect = svg.getBoundingClientRect();
        const mouseX = me.clientX - rect.left;
        const mouseY = me.clientY - rect.top;
        onDragBezierHandle(point.id, handleIndex, mouseX, mouseY);
      };

      const onUp = () => {
        setDragHandleId(null);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lane.points, onDragBezierHandle],
  );

  function handleSvgClick(e: React.MouseEvent<SVGSVGElement>) {
    if (dragPointId || dragHandleId) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const minDist = 12;
    for (const pt of lane.points) {
      const px = tc.timeToX(canvas, pt.time);
      const py = tc.valueToY(canvas, pt.value);
      const dist = Math.sqrt((x - px) ** 2 + (y - py) ** 2);
      if (dist < minDist) return;
    }

    const time = tc.xToTime(canvas, x);
    const value = tc.yToValue(canvas, y);
    onAddPoint(time, value, e.shiftKey);
  }

  function startDrag(e: React.MouseEvent, point: Point) {
    e.preventDefault();
    e.stopPropagation();
    setDragPointId(point.id);
    onSelectPoint(point.id);

    const svg = svgRef.current!;

    const onMove = (me: MouseEvent) => {
      const rect = svg.getBoundingClientRect();
      const x = me.clientX - rect.left;
      const y = me.clientY - rect.top;
      let newTime = tc.xToTime(canvas, x);
      const newValue = tc.yToValue(canvas, y);

      const idx = lane.points.findIndex((p) => p.id === point.id);
      const prev = idx > 0 ? lane.points[idx - 1]!.time : 0;
      const next =
        idx < lane.points.length - 1
          ? lane.points[idx + 1]!.time
          : tc.xToTime(canvas, width);
      newTime = Math.max(prev, Math.min(next, newTime));

      onDragPoint(
        point.id,
        Math.round(newTime * 100) / 100,
        Math.round(newValue * 1000) / 1000,
      );
    };

    const onUp = () => {
      setDragPointId(null);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="bg-zinc-950 cursor-crosshair select-none overflow-hidden"
      onClick={handleSvgClick}
      onWheel={onWheel}
    >
      {/* Defs for clipping the curve to the plottable area */}
      <defs>
        <clipPath id="plot-area">
          <rect x={48} y={0} width={width - 64} height={height} />
        </clipPath>
      </defs>

      {/* Grid lines */}
      {gridLines.map((val) => (
        <line
          key={val}
          x1={48}
          y1={tc.valueToY(canvas, val)}
          x2={width - 16}
          y2={tc.valueToY(canvas, val)}
          stroke="#27272a"
          strokeWidth={1}
        />
      ))}
      {/* Grid labels */}
      {gridLines.map((val) => (
        <text
          key={`label-${val}`}
          x={40}
          y={tc.valueToY(canvas, val) + 4}
          fill="#52525b"
          fontSize={9}
          textAnchor="end"
        >
          {val.toFixed(2)}
        </text>
      ))}

      {/* Curve segments and Control points both clipped */}
      <g clipPath="url(#plot-area)">
        {curveSegments.map((seg, i) => (
          <path
            key={i}
            d={seg.pathD}
            fill="none"
            stroke={color}
            strokeWidth={2}
            strokeLinecap="round"
            opacity={0.8}
          />
        ))}

        {/* Playback cursor */}
        {showCursor && (
          <line
            x1={cursorX}
            y1={0}
            x2={cursorX}
            y2={height}
            stroke="#facc15"
            strokeWidth={1.5}
            opacity={0.8}
            pointerEvents="none"
          />
        )}

        {/* Control points */}
        {lane.points.map((point) => (
          <g key={point.id}>
            {/* Outer ring for selected */}
            {selectedPointId === point.id && (
              <circle
                cx={tc.timeToX(canvas, point.time)}
                cy={tc.valueToY(canvas, point.value)}
                r={8}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                opacity={0.4}
                onClick={(e) => e.stopPropagation()}
              />
            )}
            {/* Point circle */}
            <circle
              cx={tc.timeToX(canvas, point.time)}
              cy={tc.valueToY(canvas, point.value)}
              r={5}
              fill={selectedPointId === point.id ? color : "#18181b"}
              stroke={color}
              strokeWidth={2}
              className={dragPointId === point.id ? "cursor-grabbing" : "cursor-grab"}
              onClick={(e) => e.stopPropagation()}
              onMouseDown={(e) => startDrag(e, point)}
              onContextMenu={(e) => { e.preventDefault(); onRemovePoint(point.id); }}
              onMouseEnter={() => setHoveredPointId(point.id)}
              onMouseLeave={() => setHoveredPointId(null)}
            />
            {/* Tooltip */}
            {(hoveredPointId === point.id || dragPointId === point.id) && (
              <g>
                <rect
                  x={tc.timeToX(canvas, point.time) - 36}
                  y={tc.valueToY(canvas, point.value) - 28}
                  width={72}
                  height={18}
                  rx={3}
                  fill="#27272a"
                  opacity={0.9}
                />
                <text
                  x={tc.timeToX(canvas, point.time)}
                  y={tc.valueToY(canvas, point.value) - 15}
                  fill="#e4e4e7"
                  fontSize={9}
                  textAnchor="middle"
                  fontFamily="monospace"
                >
                  {point.time.toFixed(1)}s · {point.value.toFixed(3)}
                </text>
              </g>
            )}

            {/* Bezier handles */}
            {selectedBezierHandles && selectedBezierHandles.pointId === point.id && (
              <g>
                <line
                  x1={selectedBezierHandles.prevX}
                  y1={selectedBezierHandles.prevY}
                  x2={selectedBezierHandles.cp1x}
                  y2={selectedBezierHandles.cp1y}
                  stroke="#a1a1aa"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  opacity={0.6}
                />
                <line
                  x1={selectedBezierHandles.currX}
                  y1={selectedBezierHandles.currY}
                  x2={selectedBezierHandles.cp2x}
                  y2={selectedBezierHandles.cp2y}
                  stroke="#a1a1aa"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  opacity={0.6}
                />
                <circle
                  cx={selectedBezierHandles.cp1x}
                  cy={selectedBezierHandles.cp1y}
                  r={4}
                  fill="#f59e0b"
                  stroke="#fbbf24"
                  strokeWidth={1.5}
                  className={dragHandleId === point.id + "-cp1" ? "cursor-grabbing" : "cursor-grab"}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => startHandleDrag(e, point, 1)}
                />
                <circle
                  cx={selectedBezierHandles.cp2x}
                  cy={selectedBezierHandles.cp2y}
                  r={4}
                  fill="#f59e0b"
                  stroke="#fbbf24"
                  strokeWidth={1.5}
                  className={dragHandleId === point.id + "-cp2" ? "cursor-grabbing" : "cursor-grab"}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => startHandleDrag(e, point, 2)}
                />
              </g>
            )}
          </g>
        ))}
      </g>

      {/* Info overlay (bottom-right) */}
      <g>
        <rect
          x={width - 130}
          y={height - 24}
          width={122}
          height={18}
          rx={3}
          fill="#18181b"
          opacity={0.8}
        />
        <text
          x={width - 125}
          y={height - 11}
          fill="#71717a"
          fontSize={9}
          fontFamily="monospace"
        >
          {lane.points.length} pts · {Math.round(canvas.zoom * 100)}%
        </text>
      </g>
    </svg>
  );
}
