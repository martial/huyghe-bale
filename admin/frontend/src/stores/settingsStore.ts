import { defineStore } from "pinia";
import { ref } from "vue";
import * as api from "../api/settings";
import type { Settings } from "../api/settings";

export const useSettingsStore = defineStore("settings", () => {
  const settings = ref<Settings>({ osc_frequency: 30 });
  const loading = ref(false);

  async function fetch() {
    loading.value = true;
    try {
      settings.value = await api.getSettings();
    } finally {
      loading.value = false;
    }
  }

  async function update(data: Partial<Settings>) {
    settings.value = await api.updateSettings(data);
  }

  return { settings, loading, fetch, update };
});
