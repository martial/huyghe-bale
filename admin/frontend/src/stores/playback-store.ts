import { create } from "zustand";
import type { PlaybackStatus } from "../types/playback";
import * as api from "../api/playback";

let pollTimer: ReturnType<typeof setInterval> | null = null;

interface PlaybackState {
  status: PlaybackStatus;
  polling: boolean;
  start: (type: "timeline" | "orchestration", id: string, device_ids: string[], lane?: "a" | "b") => Promise<void>;
  stop: () => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  seek: (elapsed: number) => Promise<void>;
  fetchStatus: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
}

export const usePlaybackStore = create<PlaybackState>((set, get) => ({
  status: {
    playing: false,
    paused: false,
    elapsed: 0,
    total_duration: 0,
    current_values: { a: 0, b: 0 },
    type: null,
    id: null,
  },
  polling: false,

  async start(type, id, device_ids, lane?) {
    await api.startPlayback({ type, id, device_ids, lane });
    get().startPolling();
  },

  async stop() {
    await api.stopPlayback();
    get().stopPolling();
    await get().fetchStatus();
  },

  async pause() {
    await api.pausePlayback();
    await get().fetchStatus();
  },

  async resume() {
    await api.resumePlayback();
    await get().fetchStatus();
  },

  async seek(elapsed) {
    await api.seekPlayback(elapsed);
  },

  async fetchStatus() {
    const status = await api.getPlaybackStatus();
    set({ status });
  },

  startPolling() {
    get().stopPolling();
    set({ polling: true });
    pollTimer = setInterval(async () => {
      await get().fetchStatus();
      if (!get().status.playing) {
        get().stopPolling();
      }
    }, 500);
  },

  stopPolling() {
    set({ polling: false });
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  },
}));
