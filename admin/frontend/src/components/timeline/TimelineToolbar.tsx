import { useNavigate } from "react-router";
import type { Timeline, Point, CurveType } from "../../types/timeline";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { downloadFromUrl } from "../../lib/download";

const curveTypes: CurveType[] = [
  "linear", "step", "ease-in", "ease-out", "ease-in-out", "sine", "exponential", "bezier",
];

interface Props {
  timeline: Timeline;
  selectedPoint: Point | null;
  onNameChange: (name: string) => void;
  onDurationChange: (duration: number) => void;
  onLoopChange: (loop: boolean) => void;
  onCurveTypeChange: (curveType: CurveType) => void;
  onSave: () => void;
}

export default function TimelineToolbar({
  timeline,
  selectedPoint,
  onNameChange,
  onDurationChange,
  onLoopChange,
  onCurveTypeChange,
  onSave,
}: Props) {
  const navigate = useNavigate();
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
    // Timelines drive the vents lane; exclude trolleys (they run their own
    // /trolley-timelines flow) so the backend's type-guard doesn't 400.
    const vents = devs.filter((d) => (d.type ?? "vents") === "vents");
    if (vents.length === 0) return;
    await start("timeline", timeline.id, vents.map((d) => d.id));
  }

  // Default to true to preserve historical behaviour.
  const isLooping = timeline.loop !== false;

  return (
    <div className="border-b border-zinc-800/60 bg-zinc-900/50">
      <div className="flex items-center gap-4 px-5 py-2.5">
        <button onClick={() => navigate("/timelines")} className="text-zinc-500 hover:text-white text-sm transition-colors">
          &larr;
        </button>

        <input
          value={timeline.name}
          onChange={(e) => onNameChange(e.target.value)}
          className="bg-transparent border-b border-zinc-700 focus:border-orange-400 outline-none text-sm font-medium px-1 py-0.5 w-48 transition-colors"
        />

        <label className="flex items-center gap-1 text-xs text-zinc-500">
          Duration
          <input
            value={timeline.duration}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            type="number"
            min={1}
            step={1}
            className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-0.5 w-16 text-sm text-zinc-200 font-mono focus:outline-none focus:border-orange-500/50 transition-colors"
          />
          <span>s</span>
        </label>

        {selectedPoint && (
          <div className="flex items-center gap-2 ml-4 pl-4 border-l border-zinc-800/60">
            <span className="text-xs text-zinc-500">Curve:</span>
            <select
              value={selectedPoint.curve_type}
              onChange={(e) => onCurveTypeChange(e.target.value as CurveType)}
              className="bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-0.5 text-xs text-zinc-200 focus:outline-none focus:border-orange-500/50 transition-colors"
            >
              {curveTypes.map((ct) => (
                <option key={ct} value={ct}>
                  {ct === "bezier" ? "custom" : ct}
                </option>
              ))}
            </select>
            <span className="text-xs text-zinc-600 font-mono">
              t={selectedPoint.time.toFixed(1)}s v={selectedPoint.value.toFixed(3)}
            </span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => onLoopChange(!isLooping)}
            title={isLooping ? "Loop is on — playback wraps at the end" : "Loop is off — playback stops at the end"}
            className={`p-1.5 rounded-lg transition-all duration-200 ${
              isLooping
                ? "bg-orange-900/40 text-orange-300 hover:bg-orange-900/60"
                : "bg-zinc-800 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 4v5h.582M4.582 9A8.001 8.001 0 0119.418 11M20 20v-5h-.581M19.419 15A8.003 8.003 0 014.582 13" />
            </svg>
          </button>
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
          <button
            onClick={() => downloadFromUrl(
              `/api/v1/export/timeline/${timeline.id}`,
              `${timeline.name || timeline.id}.json`,
            )}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm font-medium text-zinc-300 transition-all duration-200"
            title="Download timeline JSON (raw curve points)"
          >
            Export
          </button>
          <button
            onClick={() => downloadFromUrl(
              `/api/v1/export/timeline/${timeline.id}/sampled`,
              `${timeline.name || timeline.id}_sampled.json`,
            )}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm font-medium text-zinc-300 transition-all duration-200"
            title="Download frame-by-frame rendered values at the app's configured FPS (Settings → OSC frequency)"
          >
            Export sampled
          </button>
          <button
            onClick={onSave}
            className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 rounded-lg text-sm font-medium transition-all duration-200"
          >
            Save
          </button>
        </div>
      </div>

    </div>
  );
}
