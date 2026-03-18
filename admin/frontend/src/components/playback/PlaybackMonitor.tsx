import type { PlaybackStatus } from "../../types/playback";
import { useSmoothedElapsed } from "../../hooks/use-smoothed-elapsed";

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function PlaybackMonitor({ status }: { status: PlaybackStatus }) {
  const smoothElapsed = useSmoothedElapsed();
  const elapsed = status.playing ? smoothElapsed : status.elapsed;
  const progress = status.total_duration === 0 ? 0 : (elapsed / status.total_duration) * 100;

  return (
    <div className="space-y-2">
      {/* Progress bar */}
      <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-orange-500 rounded-full"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Time */}
      <div className="flex justify-between text-[10px] text-zinc-500 font-mono">
        <span>{formatTime(elapsed)}</span>
        <span>{formatTime(status.total_duration)}</span>
      </div>

      {/* Value bars */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-orange-400/70 w-3">A</span>
          <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-orange-500/60 rounded-full"
              style={{ width: `${status.current_values.a * 100}%`, transition: "width 500ms linear" }}
            />
          </div>
          <span className="text-[10px] text-zinc-500 font-mono w-8 text-right">
            {(status.current_values.a * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-sky-400/70 w-3">B</span>
          <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-sky-500/60 rounded-full"
              style={{ width: `${status.current_values.b * 100}%`, transition: "width 500ms linear" }}
            />
          </div>
          <span className="text-[10px] text-zinc-500 font-mono w-8 text-right">
            {(status.current_values.b * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
}
