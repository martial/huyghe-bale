import { create } from "zustand";
import type {
  TrolleyTimeline,
  TrolleyTimelineSummary,
} from "../types/trolley";
import * as api from "../api/trolley";

interface TrolleyState {
  list: TrolleyTimelineSummary[];
  current: TrolleyTimeline | null;
  loading: boolean;
  fetchList: () => Promise<void>;
  fetchOne: (id: string) => Promise<void>;
  createTrolleyTimeline: (
    data: Partial<TrolleyTimeline>,
  ) => Promise<TrolleyTimeline>;
  save: (tl: TrolleyTimeline) => Promise<void>;
  saveSilent: (tl: TrolleyTimeline) => Promise<void>;
  remove: (id: string) => Promise<void>;
  duplicate: (id: string) => Promise<TrolleyTimeline>;
}

export const useTrolleyStore = create<TrolleyState>((set, get) => ({
  list: [],
  current: null,
  loading: false,

  async fetchList() {
    set({ loading: true });
    try {
      const list = await api.listTrolleyTimelines();
      set({ list });
    } finally {
      set({ loading: false });
    }
  },

  async fetchOne(id: string) {
    set({ loading: true });
    try {
      const current = await api.getTrolleyTimeline(id);
      set({ current });
    } finally {
      set({ loading: false });
    }
  },

  async createTrolleyTimeline(data: Partial<TrolleyTimeline>) {
    const tl = await api.createTrolleyTimeline(data);
    await get().fetchList();
    return tl;
  },

  async save(tl: TrolleyTimeline) {
    const updated = await api.updateTrolleyTimeline(tl.id, tl);
    set({ current: updated });
    const list = await api.listTrolleyTimelines();
    set({ list });
  },

  async saveSilent(tl: TrolleyTimeline) {
    await api.updateTrolleyTimeline(tl.id, tl);
  },

  async remove(id: string) {
    await api.deleteTrolleyTimeline(id);
    const { current } = get();
    if (current?.id === id) set({ current: null });
    await get().fetchList();
  },

  async duplicate(id: string) {
    const tl = await api.duplicateTrolleyTimeline(id);
    await get().fetchList();
    return tl;
  },
}));
