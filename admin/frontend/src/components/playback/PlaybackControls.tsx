import { useEffect } from "react";
import { usePlaybackStore } from "../../stores/playback-store";
import PlaybackMonitor from "./PlaybackMonitor";

export default function PlaybackControls() {
  const status = usePlaybackStore((s) => s.status);
  const fetchStatus = usePlaybackStore((s) => s.fetchStatus);
  const stop = usePlaybackStore((s) => s.stop);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return (
    <div className="p-3">
      {status.playing ? (
        <div className="space-y-2">
          <PlaybackMonitor status={status} />
          <button
            onClick={() => stop()}
            className="w-full px-3 py-1.5 bg-red-600/80 hover:bg-red-500 rounded text-xs font-medium transition-colors"
          >
            Stop
          </button>
        </div>
      ) : (
        <div className="text-xs text-zinc-600 text-center py-2">Not playing</div>
      )}
    </div>
  );
}
