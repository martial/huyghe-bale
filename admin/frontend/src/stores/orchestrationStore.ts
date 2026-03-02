import { defineStore } from "pinia";
import { ref } from "vue";
import type { Orchestration } from "../types/orchestration";
import * as api from "../api/orchestrations";

export const useOrchestrationStore = defineStore("orchestrations", () => {
  const list = ref<Orchestration[]>([]);
  const current = ref<Orchestration | null>(null);
  const loading = ref(false);

  async function fetchList() {
    loading.value = true;
    try {
      list.value = await api.listOrchestrations();
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    loading.value = true;
    try {
      current.value = await api.getOrchestration(id);
    } finally {
      loading.value = false;
    }
  }

  async function create(data: Partial<Orchestration>) {
    const orch = await api.createOrchestration(data);
    await fetchList();
    return orch;
  }

  async function save(orchestration: Orchestration) {
    await api.updateOrchestration(orchestration.id, orchestration);
    await fetchList();
  }

  async function remove(id: string) {
    await api.deleteOrchestration(id);
    if (current.value?.id === id) current.value = null;
    await fetchList();
  }

  return { list, current, loading, fetchList, fetchOne, create, save, remove };
});
