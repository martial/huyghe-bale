import { useRef, useState, useCallback, useEffect } from "react";
import type { TrolleyEvent, TrolleyCommand } from "../../types/trolley";
import { usePlaybackStore } from "../../stores/playback-store";
import { TrolleyPlaybackCursor } from "./TrolleyPlaybackCursor";

const COMMAND_ROWS: { key: TrolleyCommand; label: string; color: string }[] = [
  { key: "position", label: "position", color: "bg-sky-400" },
  { key: "speed",    label: "speed",    color: "bg-orange-400" },
  { key: "step",     label: "step",     color: "bg-violet-400" },
  { key: "dir",      label: "dir",      color: "bg-amber-400" },
  { key: "enable",   label: "enable",   color: "bg-emerald-400" },
  { key: "stop",     label: "stop",     color: "bg-red-500" },
  { key: "home",     label: "home",     color: "bg-zinc-300" },
];

const LANE_HEIGHT = 36;
const LABEL_COL_PX = 72;

interface Props {
  timelineId: string;
  duration: number;
  events: TrolleyEvent[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onAdd: (time: number, command: TrolleyCommand) => void;
  onMove: (id: string, time: number) => void;
}

// Pick a round tick interval (seconds) so labels stay ≥ MIN_PX_PER_TICK apart
// given the current strip width. Widely-used "nice" intervals only.
const MIN_PX_PER_TICK = 50;
const NICE_INTERVALS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

function pickTickInterval(durationSec: number, stripWidthPx: number): number {
  if (stripWidthPx <= 0 || durationSec <= 0) return 1;
  const pxPerSec = stripWidthPx / durationSec;
  for (const step of NICE_INTERVALS) {
    if (pxPerSec * step >= MIN_PX_PER_TICK) return step;
  }
  return NICE_INTERVALS[NICE_INTERVALS.length - 1];
}

export default function TrolleyEventTrack({
  timelineId,
  duration,
  events,
  selectedId,
  onSelect,
  onAdd,
  onMove,
}: Props) {
  const stripRef = useRef<HTMLDivElement>(null);
  const rulerRef = useRef<HTMLDivElement>(null);
  const [stripWidth, setStripWidth] = useState(0);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  // Narrow boolean selector — otherwise this track re-renders on every
  // 500 ms status poll and drags the whole lanes grid through React.
  const showCursor = usePlaybackStore(
    (s) =>
      s.status.playing &&
      s.status.id === timelineId &&
      s.status.type === "trolley-timeline",
  );
  const seek = usePlaybackStore((s) => s.seek);

  // Measure the horizontal track so the ruler can pick a non-crowded tick step.
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    // Strip contains the label column too — ruler is only the area right of it.
    const measure = () => setStripWidth(Math.max(0, el.clientWidth - LABEL_COL_PX));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const tickStep = pickTickInterval(duration, stripWidth);

  function clientXToTime(clientX: number): number {
    const el = stripRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    // The strip wrapper includes the label column; the event area starts
    // LABEL_COL_PX in from the left. Factoring that out here is what was
    // making clicks land ~72 px * (duration / totalWidth) early.
    const xInEventArea = clientX - rect.left - LABEL_COL_PX;
    const eventAreaWidth = rect.width - LABEL_COL_PX;
    if (eventAreaWidth <= 0) return 0;
    const pct = Math.max(0, Math.min(1, xInEventArea / eventAreaWidth));
    return Math.round(pct * duration * 100) / 100;
  }

  const handleDragMove = useCallback(
    (e: MouseEvent) => {
      if (!draggingId) return;
      onMove(draggingId, clientXToTime(e.clientX));
    },
    [draggingId, duration, onMove],
  );

  const handleDragEnd = useCallback(() => setDraggingId(null), []);

  useEffect(() => {
    if (!draggingId) return;
    window.addEventListener("mousemove", handleDragMove);
    window.addEventListener("mouseup", handleDragEnd);
    return () => {
      window.removeEventListener("mousemove", handleDragMove);
      window.removeEventListener("mouseup", handleDragEnd);
    };
  }, [draggingId, handleDragMove, handleDragEnd]);

  function handleLaneClick(e: React.MouseEvent, command: TrolleyCommand) {
    if (e.target !== e.currentTarget) return;
    onAdd(clientXToTime(e.clientX), command);
  }

  function rulerClientXToTime(clientX: number): number {
    const el = rulerRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(pct * duration * 100) / 100;
  }

  function handleRulerSeek(clientX: number) {
    if (!showCursor) return;
    seek(rulerClientXToTime(clientX));
  }

  function handleRulerMouseDown(e: React.MouseEvent) {
    if (!showCursor) return;
    handleRulerSeek(e.clientX);
    // Scrub while dragging.
    const onMove = (me: MouseEvent) => handleRulerSeek(me.clientX);
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <div className="p-4 overflow-hidden">
      {/* Ruler — click/drag to seek while playing. */}
      <div className="flex">
        <div style={{ width: LABEL_COL_PX }} />
        <div
          ref={rulerRef}
          onMouseDown={handleRulerMouseDown}
          className={`relative flex-1 h-5 text-[10px] text-zinc-500 font-mono ${
            showCursor ? "cursor-col-resize" : ""
          }`}
        >
          {(() => {
            const ticks: number[] = [];
            // Always include 0; always include duration as a right-edge tick.
            for (let t = 0; t <= duration + 1e-6; t += tickStep) {
              ticks.push(Math.round(t * 100) / 100);
            }
            if (ticks[ticks.length - 1] !== duration) ticks.push(duration);
            return ticks.map((t) => {
              const pct = (t / duration) * 100;
              const display =
                tickStep < 1
                  ? `${t.toFixed(1)}s`
                  : `${Math.round(t)}s`;
              return (
                <div
                  key={t}
                  className="absolute top-0 h-full border-l border-zinc-800/60 pl-1"
                  style={{ left: `${pct}%` }}
                >
                  {display}
                </div>
              );
            });
          })()}
        </div>
      </div>

      {/* Wrapper that shares horizontal dimensions across all lanes (and the cursor). */}
      <div
        ref={stripRef}
        className="flex flex-col rounded-lg border border-white/5 bg-zinc-900/40 overflow-hidden relative"
      >
        {/* Playback cursor spans all lanes — imperatively animated via refs. */}
        {showCursor && stripWidth > 0 && (
          <TrolleyPlaybackCursor
            labelColPx={LABEL_COL_PX}
            stripWidth={stripWidth}
            duration={duration}
          />
        )}

        {COMMAND_ROWS.map(({ key, label, color }, rowIdx) => {
          const rowEvents = events.filter((e) => e.command === key);
          const isLast = rowIdx === COMMAND_ROWS.length - 1;
          return (
            <div
              key={key}
              className={`flex items-stretch ${isLast ? "" : "border-b border-zinc-800/60"}`}
              style={{ height: LANE_HEIGHT }}
            >
              <div
                className="flex items-center justify-end pr-3 text-[10px] font-mono uppercase tracking-wider text-zinc-500 bg-zinc-950/40 border-r border-zinc-800/60"
                style={{ width: LABEL_COL_PX }}
              >
                {label}
              </div>
              <div
                onClick={(e) => handleLaneClick(e, key)}
                className="relative flex-1 cursor-crosshair hover:bg-white/[0.015] transition-colors"
              >
                {rowEvents.map((ev) => {
                  const pct = Math.max(0, Math.min(100, (ev.time / duration) * 100));
                  const selected = ev.id === selectedId;
                  const valueTag =
                    ev.value !== undefined
                      ? ev.command === "step"
                        ? `${ev.value}`
                        : ev.command === "dir"
                        ? ev.value === 1
                          ? "fwd"
                          : "rev"
                        : ev.command === "enable"
                        ? ev.value === 1
                          ? "on"
                          : "off"
                        : ev.value.toFixed(2)
                      : null;
                  return (
                    <div
                      key={ev.id}
                      className="absolute top-0 bottom-0 flex items-center pointer-events-none"
                      style={{ left: `${pct}%`, transform: "translateX(-50%)" }}
                    >
                      <button
                        onMouseDown={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          onSelect(ev.id);
                          setDraggingId(ev.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className={`pointer-events-auto w-3 h-3 rounded-full ${color} ${
                          selected ? "ring-2 ring-white" : "ring-1 ring-black/40"
                        } hover:scale-125 transition-transform`}
                        title={`${ev.command}${valueTag ? ` = ${valueTag}` : ""} @ ${ev.time.toFixed(2)}s`}
                      />
                      {valueTag && (
                        <span
                          className={`ml-1 text-[9px] font-mono pointer-events-none ${
                            selected ? "text-zinc-200" : "text-zinc-400"
                          }`}
                        >
                          {valueTag}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2 text-[10px] text-zinc-600 font-mono">
        Click a lane to add that type of event · click a marker to edit · drag to move in time
      </div>
    </div>
  );
}
