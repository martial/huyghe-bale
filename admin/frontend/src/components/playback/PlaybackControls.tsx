import { useEffect, useRef } from "react";
import { usePlaybackStore } from "../../stores/playback-store";
import PlaybackMonitor from "./PlaybackMonitor";

export default function PlaybackControls() {
  const status = usePlaybackStore((s) => s.status);
  const fetchStatus = usePlaybackStore((s) => s.fetchStatus);
  const startPolling = usePlaybackStore((s) => s.startPolling);
  const polling = usePlaybackStore((s) => s.polling);
  const stop = usePlaybackStore((s) => s.stop);
  const bgPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Lightweight background poll to detect playback started externally
  useEffect(() => {
    fetchStatus();
    bgPollRef.current = setInterval(async () => {
      await fetchStatus();
      const current = usePlaybackStore.getState();
      if (current.status.playing && !current.polling) {
        current.startPolling();
      }
    }, 2000);
    return () => {
      if (bgPollRef.current) clearInterval(bgPollRef.current);
    };
  }, [fetchStatus, startPolling, polling]);

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
