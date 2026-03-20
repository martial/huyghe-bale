import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import type { Timeline, Point, CurveType, Lane } from "../../types/timeline";
import { useTimelineStore } from "../../stores/timeline-store";
import { useNotificationStore } from "../../stores/notification-store";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { useTimelineCanvas } from "../../hooks/use-timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import TimelineLane from "./TimelineLane";
import TimelineRuler from "./TimelineRuler";
import TimelineToolbar from "./TimelineToolbar";

function generateId(): string {
  return "pt_" + Math.random().toString(36).substring(2, 10);
}

export default function TimelineEditor({ timeline }: { timeline: Timeline }) {
  const save = useTimelineStore((s) => s.save);
  const notify = useNotificationStore((s) => s.notify);
  const [local, setLocal] = useState<Timeline>(() => JSON.parse(JSON.stringify(timeline)));
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgWidth, setSvgWidth] = useState(900);
  const svgHeight = 200;
  const rulerHeight = 32;
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);

  useEffect(() => {
    setLocal(JSON.parse(JSON.stringify(timeline)));
  }, [timeline]);

  useEffect(() => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setSvgWidth(rect.width);
    }
  }, []);

  const { status: playbackStatus, start: startPlayback, pause: pausePlayback, resume: resumePlayback } = usePlaybackStore();
  const { list: devices, fetchList: fetchDevices } = useDeviceStore();

  async function handlePlay() {
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    if (devs.length === 0) return;
    const ids = devs.map((d) => d.id);
    await startPlayback("timeline", local.id, ids);
  }

  const canvasA = useTimelineCanvas(svgWidth, svgHeight, local.duration);
  const canvasB = useTimelineCanvas(svgWidth, svgHeight, local.duration);

  // Sync zoom/pan from A to B
  useEffect(() => {
    if (canvasB.zoom !== canvasA.zoom) canvasB.setZoom(canvasA.zoom);
    if (canvasB.panX !== canvasA.panX) canvasB.setPanX(canvasA.panX);
  }, [canvasA.zoom, canvasA.panX, canvasB]);

  const selectedPoint = useMemo(() => {
    if (!selectedPointId) return null;
    for (const lane of [local.lanes.a, local.lanes.b]) {
      const pt = lane.points.find((p) => p.id === selectedPointId);
      if (pt) return pt;
    }
    return null;
  }, [selectedPointId, local.lanes]);

  const addPoint = useCallback((laneKey: "a" | "b", time: number, value: number, shiftKey = false) => {
    const roundedTime = Math.round(time * 100) / 100;
    const roundedValue = Math.round(value * 1000) / 1000;

    if (shiftKey) {
      const ptA: Point = { id: generateId(), time: roundedTime, value: roundedValue, curve_type: "linear", bezier_handles: null };
      const ptB: Point = { id: generateId(), time: roundedTime, value: roundedValue, curve_type: "linear", bezier_handles: null };
      setLocal((prev) => {
        const laneA: Lane = { ...prev.lanes.a, points: [...prev.lanes.a.points, ptA].sort((a, b) => a.time - b.time) };
        const laneB: Lane = { ...prev.lanes.b, points: [...prev.lanes.b.points, ptB].sort((a, b) => a.time - b.time) };
        return { ...prev, lanes: { a: laneA, b: laneB } };
      });
      setSelectedPointId(laneKey === "a" ? ptA.id : ptB.id);
    } else {
      const pt: Point = { id: generateId(), time: roundedTime, value: roundedValue, curve_type: "linear", bezier_handles: null };
      setLocal((prev) => {
        const lane: Lane = { ...prev.lanes[laneKey], points: [...prev.lanes[laneKey].points, pt].sort((a, b) => a.time - b.time) };
        return { ...prev, lanes: { ...prev.lanes, [laneKey]: lane } };
      });
      setSelectedPointId(pt.id);
    }
  }, []);

  const removePoint = useCallback((laneKey: "a" | "b", pointId: string) => {
    setLocal((prev) => {
      const lane: Lane = { ...prev.lanes[laneKey], points: prev.lanes[laneKey].points.filter((p) => p.id !== pointId) };
      return { ...prev, lanes: { ...prev.lanes, [laneKey]: lane } };
    });
    setSelectedPointId((prev) => (prev === pointId ? null : prev));
  }, []);

  const dragPoint = useCallback((laneKey: "a" | "b", id: string, time: number, value: number) => {
    setLocal((prev) => {
      const lane: Lane = {
        ...prev.lanes[laneKey],
        points: prev.lanes[laneKey].points.map((p) =>
          p.id === id ? { ...p, time, value } : p,
        ),
      };
      return { ...prev, lanes: { ...prev.lanes, [laneKey]: lane } };
    });
  }, []);

  const dragBezierHandle = useCallback((laneKey: "a" | "b", pointId: string, handleIndex: 1 | 2, mouseX: number, mouseY: number) => {
    setLocal((prev) => {
      const points = prev.lanes[laneKey].points;
      const ptIdx = points.findIndex((p) => p.id === pointId);
      if (ptIdx < 1) return prev;
      const point = points[ptIdx]!;
      const prevPt = points[ptIdx - 1]!;
      if (!point.bezier_handles) return prev;

      const canvas = laneKey === "a" ? canvasA.state : canvasB.state;
      const x0 = tc.timeToX(canvas, prevPt.time);
      const y0 = tc.valueToY(canvas, prevPt.value);
      const x1 = tc.timeToX(canvas, point.time);
      const y1 = tc.valueToY(canvas, point.value);
      const dx = x1 - x0;
      const dy = y0 - y1;

      const newHandles = { ...point.bezier_handles };
      if (handleIndex === 1) {
        newHandles.x1 = dx !== 0 ? Math.max(0, Math.min(1, (mouseX - x0) / dx)) : 0;
        newHandles.y1 = dy !== 0 ? (y0 - mouseY) / dy : 0;
      } else {
        newHandles.x2 = dx !== 0 ? Math.max(0, Math.min(1, (mouseX - x0) / dx)) : 0;
        newHandles.y2 = dy !== 0 ? (y0 - mouseY) / dy : 0;
      }

      const newPoints = points.map((p) =>
        p.id === pointId ? { ...p, bezier_handles: newHandles } : p,
      );
      const lane: Lane = { ...prev.lanes[laneKey], points: newPoints };
      return { ...prev, lanes: { ...prev.lanes, [laneKey]: lane } };
    });
  }, [canvasA.state, canvasB.state]);

  function updatePointCurveType(curveType: CurveType) {
    if (!selectedPointId) return;
    setLocal((prev) => {
      function updateLane(lane: Lane): Lane {
        return {
          ...lane,
          points: lane.points.map((p) => {
            if (p.id !== selectedPointId) return p;
            const updated = { ...p, curve_type: curveType };
            if (curveType === "bezier" && !updated.bezier_handles) {
              updated.bezier_handles = { x1: 0.25, y1: 0.0, x2: 0.75, y2: 1.0 };
            }
            return updated;
          }),
        };
      }
      return { ...prev, lanes: { a: updateLane(prev.lanes.a), b: updateLane(prev.lanes.b) } };
    });
  }

  async function handleSave() {
    await save(local);
    notify("success", "Timeline saved successfully!");
  }

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      // Ignore spacebar when focused on inputs
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === " " && tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") {
        e.preventDefault();
        if (playbackStatus.playing && !playbackStatus.paused) {
          pausePlayback();
        } else if (playbackStatus.playing && playbackStatus.paused) {
          resumePlayback();
        } else {
          handlePlay();
        }
        return;
      }
      if (e.key === "Escape") {
        setSelectedPointId(null);
        return;
      }
      const isDelete =
        (e.shiftKey && e.key === "D") || e.key === "Delete" || e.key === "Backspace";
      if (isDelete && selectedPointId) {
        e.preventDefault();
        for (const laneKey of ["a", "b"] as const) {
          const idx = local.lanes[laneKey].points.findIndex((p) => p.id === selectedPointId);
          if (idx >= 0) {
            removePoint(laneKey, selectedPointId);
            break;
          }
        }
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [selectedPointId, local.lanes, removePoint, playbackStatus.playing, playbackStatus.paused, pausePlayback, resumePlayback]);

  return (
    <div className="flex flex-col h-full" ref={containerRef}>
      <TimelineToolbar
        timeline={local}
        selectedPoint={selectedPoint}
        onNameChange={(name) => setLocal((prev) => ({ ...prev, name }))}
        onDurationChange={(duration) => setLocal((prev) => ({ ...prev, duration }))}
        onCurveTypeChange={updatePointCurveType}
        onSave={handleSave}
      />

      {/* Ruler */}
      <TimelineRuler
        width={svgWidth}
        height={rulerHeight}
        duration={local.duration}
        canvas={canvasA.state}
        timelineId={local.id}
      />

      {/* Lane A */}
      <div className="border-b border-zinc-800/60">
        <div className="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
          <span className="w-10 text-center font-medium text-orange-400/70">A</span>
          <span>{local.lanes.a.label}</span>
        </div>
        <TimelineLane
          lane={local.lanes.a}
          width={svgWidth}
          height={svgHeight}
          canvas={canvasA.state}
          selectedPointId={selectedPointId}
          color="#f97316"
          timelineId={local.id}
          onSelectPoint={setSelectedPointId}
          onAddPoint={(t, v, shift) => addPoint("a", t, v, shift)}
          onRemovePoint={(id) => removePoint("a", id)}
          onDragPoint={(id, t, v) => dragPoint("a", id, t, v)}
          onDragBezierHandle={(pid, hi, mx, my) => dragBezierHandle("a", pid, hi, mx, my)}
          onWheel={canvasA.onWheel}
        />
      </div>

      {/* Lane B */}
      <div className="border-b border-zinc-800/60">
        <div className="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
          <span className="w-10 text-center font-medium text-sky-400/70">B</span>
          <span>{local.lanes.b.label}</span>
        </div>
        <TimelineLane
          lane={local.lanes.b}
          width={svgWidth}
          height={svgHeight}
          canvas={canvasB.state}
          selectedPointId={selectedPointId}
          color="#38bdf8"
          timelineId={local.id}
          onSelectPoint={setSelectedPointId}
          onAddPoint={(t, v, shift) => addPoint("b", t, v, shift)}
          onRemovePoint={(id) => removePoint("b", id)}
          onDragPoint={(id, t, v) => dragPoint("b", id, t, v)}
          onDragBezierHandle={(pid, hi, mx, my) => dragBezierHandle("b", pid, hi, mx, my)}
          onWheel={canvasB.onWheel}
        />
      </div>

      {/* Keyboard shortcuts hint */}
      <div className="px-3 py-1.5 text-[10px] text-zinc-600 bg-zinc-900/50 border-t border-zinc-800/60 font-mono">
        Space = play/pause · Click = add point · Shift+Click = both lanes · Shift+D / Del = delete · Scroll = zoom · Esc = deselect · Drag ruler = seek
      </div>
    </div>
  );
}
