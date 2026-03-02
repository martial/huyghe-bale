import { defineStore } from "pinia";
import { ref } from "vue";
import type { Timeline, TimelineSummary } from "../types/timeline";
import * as api from "../api/timelines";

export const useTimelineStore = defineStore("timelines", () => {
  const list = ref<TimelineSummary[]>([]);
  const current = ref<Timeline | null>(null);
  const loading = ref(false);

  async function fetchList() {
    loading.value = true;
    try {
      list.value = await api.listTimelines();
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    loading.value = true;
    try {
      current.value = await api.getTimeline(id);
    } finally {
      loading.value = false;
    }
  }

  async function create(data: Partial<Timeline>) {
    const tl = await api.createTimeline(data);
    await fetchList();
    return tl;
  }

  async function save(timeline: Timeline) {
    const updated = await api.updateTimeline(timeline.id, timeline);
    current.value = updated;
    // Refresh list silently (don't set loading — that would unmount the editor)
    list.value = await api.listTimelines();
  }

  async function remove(id: string) {
    await api.deleteTimeline(id);
    if (current.value?.id === id) current.value = null;
    await fetchList();
  }

  async function duplicate(id: string) {
    const tl = await api.duplicateTimeline(id);
    await fetchList();
    return tl;
  }

  return { list, current, loading, fetchList, fetchOne, create, save, remove, duplicate };
});
