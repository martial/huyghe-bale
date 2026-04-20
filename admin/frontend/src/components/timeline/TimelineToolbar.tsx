import { useState } from "react";
import { useNavigate } from "react-router";
import type { Timeline, Point, CurveType } from "../../types/timeline";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { sendTestValue } from "../../api/devices";
import { downloadFromUrl } from "../../lib/download";

const curveTypes: CurveType[] = [
  "linear", "step", "ease-in", "ease-out", "ease-in-out", "sine", "exponential", "bezier",
];

interface Props {
  timeline: Timeline;
  selectedPoint: Point | null;
  onNameChange: (name: string) => void;
  onDurationChange: (duration: number) => void;
  onCurveTypeChange: (curveType: CurveType) => void;
  onSave: () => void;
}

export default function TimelineToolbar({
  timeline,
  selectedPoint,
  onNameChange,
  onDurationChange,
  onCurveTypeChange,
  onSave,
}: Props) {
  const navigate = useNavigate();
  const { status, start, pause, resume } = usePlaybackStore();
  const { list: devices, fetchList: fetchDevices } = useDeviceStore();

  async function handlePlay() {
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    if (devs.length === 0) return;
    const ids = devs.map((d) => d.id);
    await start("timeline", timeline.id, ids);
  }

  const [testBusy, setTestBusy] = useState(false);

  async function handleTest(method: "osc" | "http", valueA: number, valueB: number, label: string) {
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    if (devs.length === 0) return;
    const ids = devs.map((d) => d.id);
    setTestBusy(true);
    try {
      const result = await sendTestValue(ids, valueA, valueB, method);
      console.log(`[Test] ${method.toUpperCase()} ${label} result:`, result);
    } catch (e) {
      console.error(`[Test] ${method.toUpperCase()} ${label} error:`, e);
    } finally {
      setTestBusy(false);
    }
  }

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
            onClick={() => {
              if (status.playing && !status.paused) {
                pause();
              } else if (status.playing && status.paused) {
                resume();
              } else {
                handlePlay();
              }
            }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              status.playing && !status.paused
                ? "bg-yellow-600/80 hover:bg-yellow-500"
                : "bg-green-600 hover:bg-green-500"
            }`}
          >
            {status.playing && !status.paused ? "Pause" : "Play"}
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

      {/* GPIO Test Panel */}
      <div className="flex items-center gap-3 px-5 py-1.5 border-t border-zinc-800/40 bg-zinc-950/30">
        <span className="text-[10px] text-zinc-600 uppercase tracking-wider font-medium">Test</span>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-zinc-500 mr-0.5">OSC</span>
          <button disabled={testBusy} onClick={() => handleTest("osc", 1, 0, "A ON")} className="px-1.5 py-0.5 text-[10px] bg-orange-900/40 hover:bg-orange-800/60 text-orange-300/80 rounded disabled:opacity-30 transition-colors">A</button>
          <button disabled={testBusy} onClick={() => handleTest("osc", 0, 1, "B ON")} className="px-1.5 py-0.5 text-[10px] bg-sky-900/40 hover:bg-sky-800/60 text-sky-300/80 rounded disabled:opacity-30 transition-colors">B</button>
          <button disabled={testBusy} onClick={() => handleTest("osc", 0, 0, "ALL OFF")} className="px-1.5 py-0.5 text-[10px] bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 rounded disabled:opacity-30 transition-colors">OFF</button>
        </div>
        <div className="w-px h-3 bg-zinc-800/60" />
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-zinc-500 mr-0.5">HTTP</span>
          <button disabled={testBusy} onClick={() => handleTest("http", 1, 0, "A ON")} className="px-1.5 py-0.5 text-[10px] bg-orange-900/40 hover:bg-orange-800/60 text-orange-300/80 rounded disabled:opacity-30 transition-colors">A</button>
          <button disabled={testBusy} onClick={() => handleTest("http", 0, 1, "B ON")} className="px-1.5 py-0.5 text-[10px] bg-sky-900/40 hover:bg-sky-800/60 text-sky-300/80 rounded disabled:opacity-30 transition-colors">B</button>
          <button disabled={testBusy} onClick={() => handleTest("http", 0, 0, "ALL OFF")} className="px-1.5 py-0.5 text-[10px] bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 rounded disabled:opacity-30 transition-colors">OFF</button>
        </div>
      </div>
    </div>
  );
}
