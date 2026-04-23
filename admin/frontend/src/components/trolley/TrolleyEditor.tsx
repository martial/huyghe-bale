import { useState, useEffect, useRef, useMemo } from "react";
import type { TrolleyTimeline, TrolleyEvent, TrolleyCommand } from "../../types/trolley";
import { useTrolleyStore } from "../../stores/trolley-store";
import { useNotificationStore } from "../../stores/notification-store";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import TrolleyToolbar from "./TrolleyToolbar";
import TrolleyEventTrack from "./TrolleyEventTrack";
import TrolleyEventEditor from "./TrolleyEventEditor";

function generateEventId(): string {
  return "ev_" + Math.random().toString(36).substring(2, 10);
}

export default function TrolleyEditor({ timeline }: { timeline: TrolleyTimeline }) {
  const save = useTrolleyStore((s) => s.save);
  const saveSilent = useTrolleyStore((s) => s.saveSilent);
  const notify = useNotificationStore((s) => s.notify);
  const [local, setLocal] = useState<TrolleyTimeline>(() => JSON.parse(JSON.stringify(timeline)));
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    setLocal(JSON.parse(JSON.stringify(timeline)));
    setSelectedId(null);
  }, [timeline]);

  // Debounced auto-save
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    const t = setTimeout(() => {
      saveSilent(local);
    }, 500);
    return () => clearTimeout(t);
  }, [local, saveSilent]);

  const isPlaying = usePlaybackStore((s) => s.status.playing);
  const isPaused = usePlaybackStore((s) => s.status.paused);
  const start = usePlaybackStore((s) => s.start);
  const pause = usePlaybackStore((s) => s.pause);
  const resume = usePlaybackStore((s) => s.resume);
  const { list: devices, fetchList: fetchDevices } = useDeviceStore();

  async function handlePlay() {
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    const trolleys = devs.filter((d) => d.type === "trolley");
    if (trolleys.length === 0) return;
    await start("trolley-timeline", local.id, trolleys.map((d) => d.id));
  }

  const sortedEvents = useMemo(
    () => [...local.events].sort((a, b) => a.time - b.time),
    [local.events],
  );

  const selectedEvent = useMemo(
    () => local.events.find((e) => e.id === selectedId) ?? null,
    [local.events, selectedId],
  );

  function addEvent(time: number, command: TrolleyCommand) {
    const defaultValueFor = (c: TrolleyCommand): number | undefined => {
      switch (c) {
        case "position":
        case "speed":
          return 0.5;
        case "step":
          return 1000;
        case "dir":
        case "enable":
          return 1;
        default:
          return undefined; // stop, home
      }
    };
    const ev: TrolleyEvent = {
      id: generateEventId(),
      time,
      command,
      value: defaultValueFor(command),
    };
    setLocal((prev) => ({ ...prev, events: [...prev.events, ev] }));
    setSelectedId(ev.id);
  }

  function moveEvent(id: string, time: number) {
    setLocal((prev) => ({
      ...prev,
      events: prev.events.map((e) => (e.id === id ? { ...e, time } : e)),
    }));
  }

  function updateEvent(next: TrolleyEvent) {
    setLocal((prev) => ({
      ...prev,
      events: prev.events.map((e) => (e.id === next.id ? next : e)),
    }));
  }

  function deleteEvent(id: string) {
    setLocal((prev) => ({
      ...prev,
      events: prev.events.filter((e) => e.id !== id),
    }));
    setSelectedId(null);
  }

  async function handleSave() {
    await save(local);
    notify("success", "Trolley timeline saved");
  }

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === " " && tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") {
        e.preventDefault();
        if (isPlaying && !isPaused) pause();
        else if (isPlaying && isPaused) resume();
        else handlePlay();
        return;
      }
      if (e.key === "Escape") {
        setSelectedId(null);
        return;
      }
      if ((e.shiftKey && e.key === "D") || e.key === "Delete" || e.key === "Backspace") {
        if (selectedId && tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") {
          e.preventDefault();
          deleteEvent(selectedId);
        }
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [selectedId, isPlaying, isPaused, pause, resume]);

  return (
    <div className="flex flex-col h-full">
      <TrolleyToolbar
        timeline={local}
        selectedEvent={selectedEvent}
        onNameChange={(name) => setLocal((prev) => ({ ...prev, name }))}
        onDurationChange={(duration) =>
          setLocal((prev) => ({ ...prev, duration: Math.max(1, duration) }))
        }
        onSave={handleSave}
      />

      <TrolleyEventTrack
        timelineId={local.id}
        duration={local.duration}
        events={sortedEvents}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onAdd={addEvent}
        onMove={moveEvent}
      />

      {selectedEvent && (
        <TrolleyEventEditor
          event={selectedEvent}
          duration={local.duration}
          onChange={updateEvent}
          onDelete={() => deleteEvent(selectedEvent.id)}
        />
      )}

      <div className="px-3 py-1.5 text-[10px] text-zinc-600 bg-zinc-900/50 border-t border-zinc-800/60 font-mono">
        Space = play/pause · Click a lane = add event on that lane · Click marker = select · Drag marker = move · Shift+D / Del = delete · Esc = deselect
      </div>
    </div>
  );
}
