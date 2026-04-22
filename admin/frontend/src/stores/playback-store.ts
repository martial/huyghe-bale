import { create } from "zustand";
import type { PlaybackStatus } from "../types/playback";
import * as api from "../api/playback";

let pollTimer: ReturnType<typeof setInterval> | null = null;

interface PlaybackState {
  status: PlaybackStatus;
  polling: boolean;
  start: (type: "timeline" | "orchestration" | "trolley-timeline", id: string, device_ids: string[]) => Promise<void>;
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

  async start(type, id, device_ids) {
    await api.startPlayback({ type, id, device_ids });
    get().startPolling();
  },

  async stop() {
    await api.stopPlayback();
    get().stopPolling();
    await get().fetchStatus();
    // Fetch again after short delay to ensure backend has settled
    setTimeout(async () => {
      await get().fetchStatus();
      set({ status: { ...get().status, current_values: { a: 0, b: 0 } } });
    }, 300);
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
    // Background poll runs every 2s — skip the setState (and the cascade of
    // re-renders into the sidebar) when nothing actually changed.
    const prev = get().status;
    if (
      prev.playing === status.playing &&
      prev.paused === status.paused &&
      prev.elapsed === status.elapsed &&
      prev.total_duration === status.total_duration &&
      prev.current_values.a === status.current_values.a &&
      prev.current_values.b === status.current_values.b &&
      prev.type === status.type &&
      prev.id === status.id
    ) {
      return;
    }
    set({ status });
  },

  startPolling() {
    get().stopPolling();
    set({ polling: true });
    pollTimer = setInterval(async () => {
      await get().fetchStatus();
      if (!get().status.playing) {
        // One final fetch before stopping
        await get().fetchStatus();
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
