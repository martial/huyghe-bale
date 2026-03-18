import { useState, useEffect, useRef } from "react";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";

interface Props {
  type: "timeline" | "orchestration";
  id: string;
}

export default function PlaybackStartButton({ type, id }: Props) {
  const start = usePlaybackStore((s) => s.start);
  const playing = usePlaybackStore((s) => s.status.playing);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);

  const [showPicker, setShowPicker] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function toggleDevice(devId: string) {
    setSelectedIds((prev) =>
      prev.includes(devId) ? prev.filter((x) => x !== devId) : [...prev, devId],
    );
  }

  async function handleStart() {
    if (!devices.length) {
      await fetchDevices();
    }
    let ids = selectedIds;
    if (!ids.length && devices.length) {
      ids = devices.map((d) => d.id);
      setSelectedIds(ids);
    }
    if (!ids.length) {
      setShowPicker(true);
      return;
    }
    await start(type, id, ids);
    setShowPicker(false);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={handleStart}
        disabled={playing}
        className="px-4 py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-all duration-200"
      >
        Play
      </button>

      {showPicker && (
        <div className="absolute top-full mt-1 right-0 bg-zinc-900/95 backdrop-blur-sm rounded-xl border border-zinc-700/50 p-3 z-10 min-w-48 shadow-lg">
          <p className="text-xs text-zinc-400 mb-2">Select devices:</p>
          {devices.map((dev) => (
            <label
              key={dev.id}
              className="flex items-center gap-2 py-1 text-sm cursor-pointer hover:text-white transition-colors"
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(dev.id)}
                onChange={() => toggleDevice(dev.id)}
                className="rounded accent-orange-500"
              />
              {dev.name}
            </label>
          ))}
          <button
            onClick={handleStart}
            disabled={!selectedIds.length}
            className="mt-2 w-full px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded-lg text-xs font-medium transition-all duration-200"
          >
            Start
          </button>
        </div>
      )}
    </div>
  );
}
