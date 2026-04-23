import { useEffect, useRef, useState } from "react";
import type {
  UniversalTimeline,
  CurveTrack as CurveTrackData,
  BangTrack as BangTrackData,
  CurveType,
  Track,
} from "./types";
import { usePlaybackStore } from "../stores/playback-store";
import { useTimelineCanvas } from "./hooks/use-timeline-canvas";
import Toolbar from "./Toolbar";
import Ruler from "./Ruler";
import CurveTrack from "./tracks/CurveTrack";
import BangTrack from "./tracks/BangTrack";

interface Props {
  timeline: UniversalTimeline;
  /** Fired after every debounced mutation — parent persists. */
  onChange: (next: UniversalTimeline) => void;
  /** Explicit save (manual + at the end of the auto-save debounce). */
  onSave: (tl: UniversalTimeline) => Promise<void> | void;
  /** Route prefix for the back button. */
  backPath: string;
}

const CURVE_TYPES: CurveType[] = [
  "linear", "step", "ease-in", "ease-out", "ease-in-out", "sine", "exponential", "bezier",
];

export default function Editor({ timeline, onChange, onSave, backPath }: Props) {
  const readonly = !!timeline.readonly;
  const [local, setLocal] = useState<UniversalTimeline>(timeline);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeCommand, setActiveCommand] = useState<string | null>(null);

  // External → local sync (e.g. new timeline loaded)
  useEffect(() => {
    setLocal(timeline);
    setSelectedId(null);
  }, [timeline]);

  // Debounced propagation
  const initialMount = useRef(true);
  useEffect(() => {
    if (initialMount.current) {
      initialMount.current = false;
      return;
    }
    if (readonly) return;
    const t = setTimeout(() => onChange(local), 500);
    return () => clearTimeout(t);
  }, [local, onChange, readonly]);

  // Canvas for curve tracks (ignored by bang tracks)
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgWidth, setSvgWidth] = useState(900);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setSvgWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const canvas = useTimelineCanvas(svgWidth, 200, local.duration);

  const isPlaying = usePlaybackStore((s) => s.status.playing);
  const isPaused = usePlaybackStore((s) => s.status.paused);
  const pausePlayback = usePlaybackStore((s) => s.pause);
  const resumePlayback = usePlaybackStore((s) => s.resume);

  // Default the active command for the first bang track
  useEffect(() => {
    if (activeCommand) return;
    for (const track of local.tracks) {
      if (track.kind === "bang" && track.commands.length) {
        setActiveCommand(track.commands[0]!.command);
        return;
      }
    }
  }, [local.tracks, activeCommand]);

  // Keyboard: Space = play/pause/stop-back-to-handlePlay; Esc = deselect;
  // Delete/Backspace = delete selected; Shift+D also deletes.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      const isInputField = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
      if (e.key === " " && !isInputField) {
        e.preventDefault();
        if (isPlaying && !isPaused) pausePlayback();
        else if (isPlaying && isPaused) resumePlayback();
        // Play-from-cold is up to the toolbar's Play button; keyboard play requires a mount-time device list.
        return;
      }
      if (e.key === "Escape") {
        setSelectedId(null);
        return;
      }
      const isDelete =
        (e.shiftKey && e.key === "D") || e.key === "Delete" || e.key === "Backspace";
      if (isDelete && selectedId && !isInputField && !readonly) {
        e.preventDefault();
        setLocal((prev) => deleteSelected(prev, selectedId));
        setSelectedId(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isPlaying, isPaused, pausePlayback, resumePlayback, selectedId, readonly]);

  function updateTrack(updated: Track) {
    setLocal((prev) => ({
      ...prev,
      tracks: prev.tracks.map((t) => (t.id === updated.id ? updated : t)),
    }));
  }

  function patchLocal(patch: Partial<UniversalTimeline>) {
    setLocal((prev) => ({ ...prev, ...patch }));
  }

  const showCursor = isPlaying && usePlaybackStore.getState().status.id === local.id;

  // Find selected curve point (for the inspector).
  const selectedPointInfo = (() => {
    if (!selectedId) return null;
    for (const track of local.tracks) {
      if (track.kind !== "curve") continue;
      const p = track.points.find((pt) => pt.id === selectedId);
      if (p) return { track, point: p };
    }
    return null;
  })();

  function updateSelectedPointCurve(curveType: CurveType) {
    if (!selectedPointInfo) return;
    const { track, point } = selectedPointInfo;
    updateTrack({
      ...track,
      points: track.points.map((p) =>
        p.id === point.id
          ? {
              ...p,
              curveType,
              bezierHandles:
                curveType === "bezier"
                  ? p.bezierHandles ?? { x1: 0.25, y1: 0, x2: 0.75, y2: 1 }
                  : p.bezierHandles,
            }
          : p,
      ),
    });
  }

  return (
    <div className="flex flex-col h-full" ref={containerRef}>
      <Toolbar
        timeline={local}
        deviceType={local.kind}
        backPath={backPath}
        readonly={readonly}
        onNameChange={(name) => patchLocal({ name })}
        onDurationChange={(duration) => patchLocal({ duration })}
        onLoopChange={(loop) => patchLocal({ loop })}
        onSave={() => onSave(local)}
      />

      {readonly && (
        <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/30 text-[11px] text-amber-200">
          This is a built-in example. Duplicate it from the list to edit.
        </div>
      )}

      {selectedPointInfo && (
        <div className="flex items-center gap-2 px-5 py-2 bg-zinc-900/30 border-b border-zinc-800/60 text-xs">
          <span className="text-zinc-500">Curve:</span>
          <select
            value={selectedPointInfo.point.curveType}
            onChange={(e) => updateSelectedPointCurve(e.target.value as CurveType)}
            disabled={readonly}
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-0.5 text-xs text-zinc-200 focus:outline-none disabled:opacity-60"
          >
            {CURVE_TYPES.map((ct) => (
              <option key={ct} value={ct}>
                {ct === "bezier" ? "custom" : ct}
              </option>
            ))}
          </select>
          <span className="text-zinc-600 font-mono">
            t={selectedPointInfo.point.time.toFixed(2)}s
            v={selectedPointInfo.point.value.toFixed(3)}
          </span>
        </div>
      )}

      <Ruler canvas={canvas.state} height={32} duration={local.duration} showCursor={showCursor} />

      {local.tracks.map((track) => (
        <div key={track.id} className="border-b border-zinc-800/60">
          <div className="flex items-center px-2 py-1 text-xs text-zinc-500 bg-zinc-900/50">
            <span
              className="w-10 text-center font-medium"
              style={{ color: track.color, opacity: 0.9 }}
            >
              {track.kind === "curve" ? "⎈" : "⦿"}
            </span>
            <span>{track.label}</span>
          </div>
          {track.kind === "curve" ? (
            <CurveTrack
              track={track}
              canvas={canvas.state}
              height={200}
              selectedPointId={selectedId}
              showCursor={showCursor}
              readonly={readonly}
              onSelectPoint={setSelectedId}
              onChange={(next) => updateTrack(next)}
              onWheel={canvas.onWheel}
            />
          ) : (
            <BangTrackWithCommandPicker
              track={track}
              duration={local.duration}
              selectedEventId={selectedId}
              showCursor={showCursor}
              activeCommand={activeCommand}
              readonly={readonly}
              onActiveCommand={setActiveCommand}
              onSelectEvent={setSelectedId}
              onChange={(next) => updateTrack(next)}
            />
          )}
        </div>
      ))}

      <div className="px-3 py-1.5 text-[10px] text-zinc-600 bg-zinc-900/50 border-t border-zinc-800/60 font-mono">
        Space = play/pause · Click empty = add · Double-click marker = delete · Drag marker = move · Esc = deselect
      </div>
    </div>
  );
}

/** Small wrapper that shows the command row picker above a BangTrack so
 *  the user knows which row a click will add to. */
function BangTrackWithCommandPicker(props: {
  track: BangTrackData;
  duration: number;
  selectedEventId: string | null;
  showCursor: boolean;
  activeCommand: string | null;
  readonly: boolean;
  onActiveCommand: (c: string) => void;
  onSelectEvent: (id: string | null) => void;
  onChange: (t: BangTrackData) => void;
}) {
  return (
    <div className="p-2">
      <div className="flex items-center gap-1 mb-2 px-2 text-[10px] uppercase tracking-wider text-zinc-500">
        <span className="mr-2">active command</span>
        {props.track.commands.map((c) => {
          const active = props.activeCommand === c.command;
          return (
            <button
              key={c.command}
              onClick={() => props.onActiveCommand(c.command)}
              className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                active
                  ? "bg-white/10 text-white ring-1"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              style={active ? { boxShadow: `inset 0 0 0 1px ${c.color}`, color: c.color } : undefined}
            >
              {c.command}
            </button>
          );
        })}
      </div>
      <BangTrack
        track={props.track}
        duration={props.duration}
        selectedEventId={props.selectedEventId}
        showCursor={props.showCursor}
        activeCommand={props.activeCommand}
        readonly={props.readonly}
        onSelectEvent={props.onSelectEvent}
        onChange={props.onChange}
      />
    </div>
  );
}

function deleteSelected(tl: UniversalTimeline, id: string): UniversalTimeline {
  return {
    ...tl,
    tracks: tl.tracks.map((t) => {
      if (t.kind === "curve") {
        const filtered = (t as CurveTrackData).points.filter((p) => p.id !== id);
        if (filtered.length === t.points.length) return t;
        return { ...t, points: filtered };
      }
      const filtered = (t as BangTrackData).events.filter((e) => e.id !== id);
      if (filtered.length === t.events.length) return t;
      return { ...t, events: filtered };
    }),
  };
}
