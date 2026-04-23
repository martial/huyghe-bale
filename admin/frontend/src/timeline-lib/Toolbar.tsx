import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import type { UniversalTimeline, TimelineKind } from "./types";
import { usePlaybackStore } from "../stores/playback-store";
import { useDeviceStore } from "../stores/device-store";
import { useNotificationStore } from "../stores/notification-store";
import DeviceMultiSelect from "../components/playback/DeviceMultiSelect";

interface Props {
  timeline: UniversalTimeline;
  deviceType: TimelineKind;
  /** Route prefix for the back button (/vents or /trolleys). */
  backPath: string;
  readonly?: boolean;
  onNameChange: (name: string) => void;
  onDurationChange: (seconds: number) => void;
  onLoopChange: (loop: boolean) => void;
  onSave: () => void;
}

/** Shared header strip: back button, name, duration, loop toggle,
 *  device multi-select, play/pause, save. Works for both vents and
 *  trolley timelines via the deviceType prop. */
export default function Toolbar({
  timeline,
  deviceType,
  backPath,
  readonly = false,
  onNameChange,
  onDurationChange,
  onLoopChange,
  onSave,
}: Props) {
  const navigate = useNavigate();
  const isPlaying = usePlaybackStore((s) => s.status.playing);
  const isPaused = usePlaybackStore((s) => s.status.paused);
  const playingId = usePlaybackStore((s) => s.status.id);
  const start = usePlaybackStore((s) => s.start);
  const pause = usePlaybackStore((s) => s.pause);
  const resume = usePlaybackStore((s) => s.resume);
  // Only treat the play/pause toggle as "ours" when this exact timeline is
  // what's currently playing. Otherwise the button must act as "start this
  // one" (handlePlay) — the backend's start handler stops any prior run.
  const isOurs = isPlaying && playingId === timeline.id;
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const notify = useNotificationStore((s) => s.notify);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    const eligible = devices.filter((d) => (d.type ?? "vents") === deviceType);
    setSelectedIds((prev) =>
      prev.length === 0 ? eligible.map((d) => d.id) : prev,
    );
  }, [devices, deviceType]);

  const accent =
    deviceType === "vents"
      ? "focus:border-orange-400"
      : "focus:border-sky-400";
  const saveBtn =
    deviceType === "vents"
      ? "bg-orange-600 hover:bg-orange-500"
      : "bg-sky-600 hover:bg-sky-500";

  async function handlePlay() {
    console.log("[Toolbar] Play clicked", {
      timelineId: timeline.id,
      deviceType,
      deviceCount: devices.length,
      selectedIds,
    });
    let devs = devices;
    if (devs.length === 0) {
      await fetchDevices();
      devs = useDeviceStore.getState().list;
    }
    const eligible = devs.filter((d) => (d.type ?? "vents") === deviceType);
    if (eligible.length === 0) {
      notify(
        "info",
        `No ${deviceType} devices registered — add one on the Devices page.`,
      );
      return;
    }
    // Always derive ids from the LIVE eligible list — any selectedIds
    // that no longer match a registered device are stale (added then
    // removed, or a fresh backend replaced the data-dir) and would
    // cause the backend to 400 with "No valid devices specified".
    const liveIds = eligible.map((d) => d.id);
    const ids =
      selectedIds.length > 0
        ? selectedIds.filter((id) => liveIds.includes(id))
        : liveIds;
    if (ids.length === 0) {
      // Fall back to every eligible device rather than silently no-op.
      if (liveIds.length > 0) {
        ids.push(...liveIds);
      } else {
        notify("info", `No ${deviceType} targets selected — pick at least one device.`);
        return;
      }
    }
    const serverType = deviceType === "vents" ? "timeline" : "trolley-timeline";
    try {
      await start(serverType, timeline.id, ids);
      console.log(
        "[Toolbar] start() resolved — status:",
        usePlaybackStore.getState().status,
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[Toolbar] start() threw:", e);
      notify("error", `Playback failed to start: ${msg}`);
    }
  }

  const isLooping = timeline.loop !== false;

  return (
    <div className="border-b border-zinc-800/60 bg-zinc-900/50">
      <div className="flex items-center gap-4 px-5 py-2.5">
        <button
          onClick={() => navigate(backPath)}
          className="text-zinc-500 hover:text-white text-sm transition-colors"
        >
          &larr;
        </button>

        <input
          value={timeline.name}
          readOnly={readonly}
          disabled={readonly}
          onChange={(e) => onNameChange(e.target.value)}
          className={`bg-transparent border-b border-zinc-700 ${accent} outline-none text-sm font-medium px-1 py-0.5 w-56 transition-colors disabled:opacity-60`}
        />

        <label className="flex items-center gap-1 text-xs text-zinc-500">
          Duration
          <input
            value={timeline.duration}
            readOnly={readonly}
            disabled={readonly}
            onChange={(e) => onDurationChange(Math.max(1, Number(e.target.value)))}
            type="number"
            min={1}
            step={1}
            className={`bg-zinc-800 border border-zinc-700/50 rounded-lg px-2 py-0.5 w-20 text-sm text-zinc-200 font-mono focus:outline-none ${accent} transition-colors disabled:opacity-60`}
          />
          <span>s</span>
        </label>

        <div className="ml-auto flex items-center gap-2">
          <DeviceMultiSelect
            type={deviceType}
            selected={selectedIds}
            onChange={setSelectedIds}
          />
          <button
            onClick={() => onLoopChange(!isLooping)}
            title={
              isLooping
                ? "Loop on — playback wraps at the end"
                : "Loop off — playback stops at the end"
            }
            disabled={readonly}
            className={`p-1.5 rounded-lg transition-all duration-200 disabled:opacity-40 ${
              isLooping
                ? deviceType === "vents"
                  ? "bg-orange-900/40 text-orange-300 hover:bg-orange-900/60"
                  : "bg-sky-900/40 text-sky-300 hover:bg-sky-900/60"
                : "bg-zinc-800 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M4 4v5h.582M4.582 9A8.001 8.001 0 0119.418 11M20 20v-5h-.581M19.419 15A8.003 8.003 0 014.582 13"
              />
            </svg>
          </button>
          <button
            onClick={() => {
              if (isOurs && !isPaused) pause();
              else if (isOurs && isPaused) resume();
              else handlePlay();
            }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              isOurs && !isPaused
                ? "bg-yellow-600/80 hover:bg-yellow-500"
                : "bg-green-600 hover:bg-green-500"
            }`}
          >
            {isOurs && !isPaused ? "Pause" : "Play"}
          </button>
          {!readonly && (
            <button
              onClick={onSave}
              className={`px-4 py-1.5 ${saveBtn} rounded-lg text-sm font-medium transition-all duration-200`}
            >
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
