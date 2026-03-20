import { create } from "zustand";
import type { Timeline, TimelineSummary } from "../types/timeline";
import * as api from "../api/timelines";

interface TimelineState {
  list: TimelineSummary[];
  current: Timeline | null;
  loading: boolean;
  fetchList: () => Promise<void>;
  fetchOne: (id: string) => Promise<void>;
  createTimeline: (data: Partial<Timeline>) => Promise<Timeline>;
  save: (timeline: Timeline) => Promise<void>;
  saveSilent: (timeline: Timeline) => Promise<void>;
  remove: (id: string) => Promise<void>;
  duplicate: (id: string) => Promise<Timeline>;
}

export const useTimelineStore = create<TimelineState>((set, get) => ({
  list: [],
  current: null,
  loading: false,

  async fetchList() {
    set({ loading: true });
    try {
      const list = await api.listTimelines();
      set({ list });
    } finally {
      set({ loading: false });
    }
  },

  async fetchOne(id: string) {
    set({ loading: true });
    try {
      const current = await api.getTimeline(id);
      set({ current });
    } finally {
      set({ loading: false });
    }
  },

  async createTimeline(data: Partial<Timeline>) {
    const tl = await api.createTimeline(data);
    await get().fetchList();
    return tl;
  },

  async save(timeline: Timeline) {
    const updated = await api.updateTimeline(timeline.id, timeline);
    set({ current: updated });
    const list = await api.listTimelines();
    set({ list });
  },

  async saveSilent(timeline: Timeline) {
    await api.updateTimeline(timeline.id, timeline);
  },

  async remove(id: string) {
    await api.deleteTimeline(id);
    const { current } = get();
    if (current?.id === id) set({ current: null });
    await get().fetchList();
  },

  async duplicate(id: string) {
    const tl = await api.duplicateTimeline(id);
    await get().fetchList();
    return tl;
  },
}));
