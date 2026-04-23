import { useCallback, useEffect, useRef, useState } from "react";
import type { BangTrack as BangTrackData, BangEvent } from "../types";
import { PlaybackCursorDom } from "../PlaybackCursorDom";

interface Props {
  track: BangTrackData;
  duration: number;
  selectedEventId: string | null;
  showCursor: boolean;
  /** Which command a click-to-add creates. Editor holds this state. */
  activeCommand: string | null;
  readonly?: boolean;
  onSelectEvent: (id: string | null) => void;
  onChange: (next: BangTrackData) => void;
}

const LANE_HEIGHT = 32;
const LABEL_COL_PX = 96;

function genId(): string {
  return "ev_" + Math.random().toString(36).substring(2, 10);
}

export default function BangTrack({
  track,
  duration,
  selectedEventId,
  showCursor,
  activeCommand,
  readonly = false,
  onSelectEvent,
  onChange,
}: Props) {
  const stripRef = useRef<HTMLDivElement>(null);
  const [stripWidth, setStripWidth] = useState(0);
  const [dragId, setDragId] = useState<string | null>(null);

  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
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

  const commands = track.commands;
  const events = track.events;
  void activeCommand; // reserved for a future "paint" interaction

  const clientXToTime = useCallback(
    (clientX: number): number => {
      const el = stripRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      const eventAreaLeft = rect.left + LABEL_COL_PX;
      const eventAreaWidth = rect.width - LABEL_COL_PX;
      if (eventAreaWidth <= 0) return 0;
      const pct = Math.max(0, Math.min(1, (clientX - eventAreaLeft) / eventAreaWidth));
      return Math.round(pct * duration * 100) / 100;
    },
    [duration],
  );

  function handleLaneClick(e: React.MouseEvent, commandName: string) {
    if (readonly) return;
    if (e.target !== e.currentTarget) return;
    const cmd = commands.find((c) => c.command === commandName);
    if (!cmd) return;
    const ev: BangEvent = {
      id: genId(),
      time: clientXToTime(e.clientX),
      command: commandName,
      value: cmd.valueKind === "none" ? undefined : cmd.defaultValue ?? 0,
    };
    onChange({ ...track, events: [...events, ev].sort((a, b) => a.time - b.time) });
    onSelectEvent(ev.id);
  }

  const startDrag = useCallback(
    (e: React.MouseEvent, evId: string) => {
      if (readonly) return;
      e.stopPropagation();
      e.preventDefault();
      onSelectEvent(evId);
      setDragId(evId);
      function onMove(me: MouseEvent) {
        const t = clientXToTime(me.clientX);
        onChange({
          ...track,
          events: events.map((e) => (e.id === evId ? { ...e, time: t } : e)),
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
    [clientXToTime, events, onChange, onSelectEvent, readonly, track],
  );

  return (
    <div
      ref={stripRef}
      className="flex flex-col rounded-lg border border-white/5 bg-zinc-900/40 overflow-hidden relative"
    >
      {showCursor && stripWidth > 0 && (
        <PlaybackCursorDom
          timeToX={(t) => {
            if (duration <= 0) return LABEL_COL_PX;
            const pct = Math.max(0, Math.min(1, t / duration));
            return LABEL_COL_PX + pct * stripWidth;
          }}
        />
      )}

      {commands.map((cmd, rowIdx) => {
        const isLast = rowIdx === commands.length - 1;
        const rowEvents = events.filter((ev) => ev.command === cmd.command);
        const isActive = activeCommand === cmd.command;
        return (
          <div
            key={cmd.command}
            className={`flex items-stretch ${isLast ? "" : "border-b border-zinc-800/60"}`}
            style={{ height: LANE_HEIGHT }}
          >
            <div
              className={`flex items-center justify-between pr-3 pl-3 text-[10px] font-mono uppercase tracking-wider border-r border-zinc-800/60 ${
                isActive ? "bg-zinc-800 text-zinc-200" : "bg-zinc-950/40 text-zinc-500"
              }`}
              style={{ width: LABEL_COL_PX }}
              title={isActive ? "Clicks add on this row" : "Click to select row"}
            >
              <span
                className="inline-block w-1.5 h-1.5 rounded-full mr-2 shrink-0"
                style={{ backgroundColor: cmd.color }}
              />
              <span className="flex-1 truncate">{cmd.command}</span>
            </div>
            <div
              onClick={(e) => handleLaneClick(e, cmd.command)}
              className={`relative flex-1 ${readonly ? "" : "cursor-crosshair hover:bg-white/[0.015]"} transition-colors`}
            >
              {rowEvents.map((ev) => {
                const pct = Math.max(0, Math.min(100, (ev.time / Math.max(0.001, duration)) * 100));
                const selected = ev.id === selectedEventId;
                const valueTag =
                  ev.value === undefined
                    ? null
                    : cmd.valueKind === "enum" && cmd.enumOptions
                    ? cmd.enumOptions.find((o) => o.value === ev.value)?.label ?? String(ev.value)
                    : cmd.valueKind === "int"
                    ? String(ev.value)
                    : ev.value.toFixed(2);
                return (
                  <div
                    key={ev.id}
                    className="absolute top-0 bottom-0 flex items-center pointer-events-none"
                    style={{ left: `${pct}%`, transform: "translateX(-50%)" }}
                  >
                    <button
                      onMouseDown={(e) => startDrag(e, ev.id)}
                      onClick={(e) => e.stopPropagation()}
                      className={`pointer-events-auto w-3 h-3 rounded-full ${
                        selected ? "ring-2 ring-white" : "ring-1 ring-black/40"
                      } hover:scale-125 transition-transform ${dragId === ev.id ? "scale-125" : ""}`}
                      style={{ backgroundColor: cmd.color }}
                      title={`${cmd.command}${valueTag ? ` = ${valueTag}` : ""} @ ${ev.time.toFixed(2)}s`}
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
  );
}
