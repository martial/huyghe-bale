import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import type { Point, CurveType, Lane } from "../../types/timeline";
import type { TrolleyTimeline, TrolleyLane } from "../../types/trolley";
import { useTrolleyStore } from "../../stores/trolley-store";
import { useNotificationStore } from "../../stores/notification-store";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { useTimelineCanvas } from "../../hooks/use-timeline-canvas";
import * as tc from "../../lib/timeline-canvas";
import TimelineLane from "../timeline/TimelineLane";
import TimelineRuler from "../timeline/TimelineRuler";
import TrolleyToolbar from "./TrolleyToolbar";

function generateId(): string {
  return "pt_" + Math.random().toString(36).substring(2, 10);
}

export default function TrolleyEditor({ timeline }: { timeline: TrolleyTimeline }) {
  const save = useTrolleyStore((s) => s.save);
  const saveSilent = useTrolleyStore((s) => s.saveSilent);
  const notify = useNotificationStore((s) => s.notify);
  const [local, setLocal] = useState<TrolleyTimeline>(() => JSON.parse(JSON.stringify(timeline)));
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgWidth, setSvgWidth] = useState(900);
  const svgHeight = 220;
  const rulerHeight = 32;
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);

  useEffect(() => {
    setLocal(JSON.parse(JSON.stringify(timeline)));
  }, [timeline]);

  // Auto-save on changes (debounced)
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    const timer = setTimeout(() => {
      saveSilent(local);
    }, 500);
    return () => clearTimeout(timer);
  }, [local, saveSilent]);

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
    const trolleys = devs.filter((d) => d.type === "trolley");
    if (trolleys.length === 0) return;
    const ids = trolleys.map((d) => d.id);
    await startPlayback("trolley-timeline", local.id, ids);
  }

  const canvas = useTimelineCanvas(svgWidth, svgHeight, local.duration);

  const selectedPoint = useMemo(() => {
    if (!selectedPointId) return null;
    return local.lane.points.find((p) => p.id === selectedPointId) ?? null;
  }, [selectedPointId, local.lane]);

  const addPoint = useCallback((time: number, value: number) => {
    const roundedTime = Math.round(time * 100) / 100;
    const roundedValue = Math.round(value * 1000) / 1000;
    const pt: Point = {
      id: generateId(),
      time: roundedTime,
      value: roundedValue,
      curve_type: "linear",
      bezier_handles: null,
    };
    setLocal((prev) => {
      const lane: TrolleyLane = {
        ...prev.lane,
        points: [...prev.lane.points, pt].sort((a, b) => a.time - b.time),
      };
      return { ...prev, lane };
    });
    setSelectedPointId(pt.id);
  }, []);

  const removePoint = useCallback((pointId: string) => {
    setLocal((prev) => ({
      ...prev,
      lane: { ...prev.lane, points: prev.lane.points.filter((p) => p.id !== pointId) },
    }));
    setSelectedPointId((prev) => (prev === pointId ? null : prev));
  }, []);

  const dragPoint = useCallback((id: string, time: number, value: number) => {
    setLocal((prev) => ({
      ...prev,
      lane: {
        ...prev.lane,
        points: prev.lane.points.map((p) => (p.id === id ? { ...p, time, value } : p)),
      },
    }));
  }, []);

  const dragBezierHandle = useCallback(
    (pointId: string, handleIndex: 1 | 2, mouseX: number, mouseY: number) => {
      setLocal((prev) => {
        const points = prev.lane.points;
        const ptIdx = points.findIndex((p) => p.id === pointId);
        if (ptIdx < 1) return prev;
        const point = points[ptIdx]!;
        const prevPt = points[ptIdx - 1]!;
        if (!point.bezier_handles) return prev;

        const x0 = tc.timeToX(canvas.state, prevPt.time);
        const y0 = tc.valueToY(canvas.state, prevPt.value);
        const x1 = tc.timeToX(canvas.state, point.time);
        const y1 = tc.valueToY(canvas.state, point.value);
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
        return { ...prev, lane: { ...prev.lane, points: newPoints } };
      });
    },
    [canvas.state],
  );

  function updatePointCurveType(curveType: CurveType) {
    if (!selectedPointId) return;
    setLocal((prev) => ({
      ...prev,
      lane: {
        ...prev.lane,
        points: prev.lane.points.map((p) => {
          if (p.id !== selectedPointId) return p;
          const updated: Point = { ...p, curve_type: curveType };
          if (curveType === "bezier" && !updated.bezier_handles) {
            updated.bezier_handles = { x1: 0.25, y1: 0.0, x2: 0.75, y2: 1.0 };
          }
          return updated;
        }),
      },
    }));
  }

  async function handleSave() {
    await save(local);
    notify("success", "Trolley timeline saved");
  }

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
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
        removePoint(selectedPointId);
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [selectedPointId, removePoint, playbackStatus.playing, playbackStatus.paused, pausePlayback, resumePlayback]);

  // The TimelineLane component needs a `Lane` shape from types/timeline; our
  // TrolleyLane is structurally identical (label + points), so pass through.
  const laneForRender: Lane = local.lane as unknown as Lane;

  return (
    <div className="flex flex-col h-full" ref={containerRef}>
      <TrolleyToolbar
        timeline={local}
        selectedPoint={selectedPoint}
        onNameChange={(name) => setLocal((prev) => ({ ...prev, name }))}
        onDurationChange={(duration) => setLocal((prev) => ({ ...prev, duration }))}
        onCurveTypeChange={updatePointCurveType}
        onSave={handleSave}
      />

      <TimelineRuler
        width={svgWidth}
        height={rulerHeight}
        duration={local.duration}
        canvas={canvas.state}
        timelineId={local.id}
      />

      <div className="border-b border-zinc-800/60">
        <div className="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
          <span className="w-10 text-center font-medium text-sky-400/70">P</span>
          <span>{local.lane.label || "Position (0 = home, 1 = far end)"}</span>
        </div>
        <TimelineLane
          lane={laneForRender}
          width={svgWidth}
          height={svgHeight}
          canvas={canvas.state}
          selectedPointId={selectedPointId}
          color="#38bdf8"
          timelineId={local.id}
          playbackType="trolley-timeline"
          onSelectPoint={setSelectedPointId}
          onAddPoint={(t, v) => addPoint(t, v)}
          onRemovePoint={removePoint}
          onDragPoint={dragPoint}
          onDragBezierHandle={dragBezierHandle}
          onWheel={canvas.onWheel}
        />
      </div>

      <div className="px-3 py-1.5 text-[10px] text-zinc-600 bg-zinc-900/50 border-t border-zinc-800/60 font-mono">
        Space = play/pause · Click = add point · Shift+D / Del = delete · Scroll = zoom · Esc = deselect · Drag ruler = seek
      </div>
    </div>
  );
}
