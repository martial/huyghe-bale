import { create } from "zustand";
import type { Orchestration } from "../types/orchestration";
import * as api from "../api/orchestrations";

interface OrchestrationState {
  list: Orchestration[];
  current: Orchestration | null;
  loading: boolean;
  fetchList: () => Promise<void>;
  fetchOne: (id: string) => Promise<void>;
  createOrchestration: (data: Partial<Orchestration>) => Promise<Orchestration>;
  save: (orchestration: Orchestration) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useOrchestrationStore = create<OrchestrationState>((set, get) => ({
  list: [],
  current: null,
  loading: false,

  async fetchList() {
    set({ loading: true });
    try {
      const list = await api.listOrchestrations();
      set({ list });
    } finally {
      set({ loading: false });
    }
  },

  async fetchOne(id: string) {
    set({ loading: true });
    try {
      const current = await api.getOrchestration(id);
      set({ current });
    } finally {
      set({ loading: false });
    }
  },

  async createOrchestration(data: Partial<Orchestration>) {
    const orch = await api.createOrchestration(data);
    await get().fetchList();
    return orch;
  },

  async save(orchestration: Orchestration) {
    await api.updateOrchestration(orchestration.id, orchestration);
    await get().fetchList();
  },

  async remove(id: string) {
    await api.deleteOrchestration(id);
    const { current } = get();
    if (current?.id === id) set({ current: null });
    await get().fetchList();
  },
}));
