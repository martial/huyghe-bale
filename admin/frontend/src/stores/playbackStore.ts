import { defineStore } from "pinia";
import { ref } from "vue";
import type { PlaybackStatus } from "../types/playback";
import * as api from "../api/playback";

export const usePlaybackStore = defineStore("playback", () => {
  const status = ref<PlaybackStatus>({
    playing: false,
    elapsed: 0,
    total_duration: 0,
    current_values: { a: 0, b: 0 },
    type: null,
    id: null,
  });
  const polling = ref(false);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function start(type: "timeline" | "orchestration", id: string, device_ids: string[]) {
    await api.startPlayback({ type, id, device_ids });
    startPolling();
  }

  async function stop() {
    await api.stopPlayback();
    stopPolling();
    await fetchStatus();
  }

  async function fetchStatus() {
    status.value = await api.getPlaybackStatus();
  }

  function startPolling() {
    stopPolling();
    polling.value = true;
    pollTimer = setInterval(async () => {
      await fetchStatus();
      if (!status.value.playing) {
        stopPolling();
      }
    }, 500);
  }

  function stopPolling() {
    polling.value = false;
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  return { status, polling, start, stop, fetchStatus, startPolling, stopPolling };
});
