import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import type { TrolleyTimeline, TrolleyEvent } from "../../types/trolley";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import DeviceMultiSelect from "../playback/DeviceMultiSelect";

interface Props {
  timeline: TrolleyTimeline;
  selectedEvent: TrolleyEvent | null;
  readonly?: boolean;
  onNameChange: (name: string) => void;
  onDurationChange: (duration: number) => void;
  onSave: () => void;
}

export default function TrolleyToolbar({
  timeline,
  selectedEvent,
  readonly = false,
  onNameChange,
  onDurationChange,
  onSave,
}: Props) {
  const navigate = useNavigate();
  const isPlaying = usePlaybackStore((s) => s.isPlaying);
  const isPaused = usePlaybackStore((s) => s.isPaused);
  const start = usePlaybackStore((s) => s.start);
  const pause = usePlaybackStore((s) => s.pause);
  const resume = usePlaybackStore((s) => s.resume);
  const { list: devices, fetchList: fetchDevices } = useDeviceStore();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  useEffect(() => {
    const trolleys = devices.filter((d) => d.type === "trolley");
    setSelectedIds((prev) => (prev.length === 0 ? trolleys.map((d) => d.id) : prev));
  }, [devices]);

  async function handlePlay() {
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    const trolleys = devs.filter((d) => d.type === "trolley");
    const ids = selectedIds.length > 0
      ? selectedIds.filter((id) => trolleys.some((d) => d.id === id))
      : trolleys.map((d) => d.id);
    if (ids.length === 0) return;
    await start("trolley-timeline", timeline.id, ids);
  }

  return (
    <div className="border-b border-zinc-800/60 bg-zinc-900/50">
      <div className="flex items-center gap-4 px-5 py-2.5">
        <button
          onClick={() => navigate("/trolleys")}
          className="text-zinc-500 hover:text-white text-sm transition-colors"
        >
          &larr;
        </button>

        <input
          value={timeline.name}
          readOnly={readonly}
          disabled={readonly}
          onChange={(e) => onNameChange(e.target.value)}
          className="bg-transparent border-b border-zinc-700 focus:border-sky-400 outline-none text-sm font-medium px-1 py-0.5 w-48 transition-colors disabled:opacity-60"
        />

        <label className="flex items-center gap-1 text-xs text-zinc-500">
          Duration
          <input
            value={timeline.duration}
            readOnly={readonly}
            disabled={readonly}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            type="number"
            min={1}
            step={1}
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-0.5 w-16 text-sm text-zinc-200 font-mono focus:outline-none focus:border-sky-500/50 transition-colors disabled:opacity-60"
          />
          <span>s</span>
        </label>

        {selectedEvent && (
          <div className="flex items-center gap-2 ml-4 pl-4 border-l border-zinc-800/60 text-xs text-zinc-500">
            <span className="font-medium text-zinc-300">{selectedEvent.command}</span>
            <span className="font-mono">
              t={selectedEvent.time.toFixed(2)}s
            </span>
            {selectedEvent.value !== undefined && (
              <span className="font-mono">
                v={selectedEvent.value}
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <DeviceMultiSelect type="trolley" selected={selectedIds} onChange={setSelectedIds} />
          <button
            onClick={() => {
              if (isPlaying && !isPaused) {
                pause();
              } else if (isPlaying && isPaused) {
                resume();
              } else {
                handlePlay();
              }
            }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              isPlaying && !isPaused
                ? "bg-yellow-600/80 hover:bg-yellow-500"
                : "bg-green-600 hover:bg-green-500"
            }`}
          >
            {isPlaying && !isPaused ? "Pause" : "Play"}
          </button>
          {!readonly && (
            <button
              onClick={onSave}
              className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 rounded-lg text-sm font-medium transition-all duration-200"
            >
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
